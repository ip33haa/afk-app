"""YuNet detection and SFace embeddings for one enrolled person."""

from __future__ import annotations

import threading

import cv2
import numpy as np

from app.paths import SFACE_NAME, YUNET_NAME, data_dir, model_path


class FaceEngine:
    def __init__(self, threshold: float = 0.45) -> None:
        self.threshold = threshold
        self.error = ""
        self._detector = None
        self._recognizer = None
        self._enrolled: np.ndarray | None = None
        self._guard = threading.Lock()
        self._load_models()
        self.reload()

    @property
    def ready(self) -> bool:
        return self._detector is not None and self._recognizer is not None

    def has_enrollment(self) -> bool:
        return self._enrolled is not None

    def reload(self) -> None:
        path = data_dir() / "face.npy"
        if not path.exists():
            self._enrolled = None
            return
        vector = np.load(path).astype(np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        self._enrolled = vector / norm if norm > 1e-6 else None

    def save_enrollment(self, vectors: list[np.ndarray]) -> None:
        if len(vectors) < 8:
            raise ValueError("Need at least 8 clear looks at the camera.")
        stack = np.stack([np.asarray(v, dtype=np.float32).reshape(-1) for v in vectors])
        mean = stack.mean(axis=0)
        norm = float(np.linalg.norm(mean))
        if norm < 1e-6:
            raise ValueError("Could not read a face clearly enough.")
        mean = (mean / norm).astype(np.float32)
        np.save(data_dir() / "face.npy", mean)
        self._enrolled = mean

    def largest_box(self, frame):
        """Pixel box of the closest face, or None."""
        if not self.ready or frame is None:
            return None
        with self._guard:
            face = self._largest_face(frame)
        if face is None:
            return None
        return tuple(int(value) for value in face[:4])

    def embed(self, frame) -> np.ndarray | None:
        if not self.ready:
            return None
        with self._guard:
            return self._embed_locked(frame)

    def matches(self, frame) -> tuple[bool, float]:
        """Whether the largest face is the enrolled person, and the cosine score."""
        if self._enrolled is None:
            return False, 0.0
        embedding = self.embed(frame)
        if embedding is None:
            return False, 0.0
        score = float(np.dot(embedding, self._enrolled))
        return score >= self.threshold, score

    def _load_models(self) -> None:
        yunet = model_path(YUNET_NAME)
        sface = model_path(SFACE_NAME)
        if not yunet.exists() or not sface.exists():
            self.error = "Face models are missing. Run install.ps1."
            return
        self._detector = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), 0.7, 0.3, 5000)
        self._recognizer = cv2.FaceRecognizerSF.create(str(sface), "")
        self.error = ""

    def _largest_face(self, frame):
        if frame is None or self._detector is None:
            return None
        height, width = frame.shape[:2]
        self._detector.setInputSize((width, height))
        _retval, faces = self._detector.detect(frame)
        if faces is None or len(faces) == 0:
            return None
        areas = faces[:, 2] * faces[:, 3]
        face = faces[int(np.argmax(areas))]
        if float(face[2]) < 40 or float(face[3]) < 40:
            return None
        return face

    def _embed_locked(self, frame) -> np.ndarray | None:
        if self._recognizer is None:
            return None
        face = self._largest_face(frame)
        if face is None:
            return None
        aligned = self._recognizer.alignCrop(frame, face)
        feature = self._recognizer.feature(aligned)
        vector = np.asarray(feature, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm < 1e-6:
            return None
        return vector / norm
