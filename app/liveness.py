"""A blink is required before unlock so a still photo is less likely to pass."""

from __future__ import annotations

import cv2
import numpy as np

from app.paths import LANDMARKER_NAME, model_path

# Face-mesh eye corners and lids: outer, upper, upper, inner, lower, lower.
_RIGHT_EYE = (33, 160, 158, 133, 153, 144)
_LEFT_EYE = (362, 385, 387, 263, 373, 380)
_CLOSED = 0.20
_OPEN = 0.25


class BlinkDetector:
    def __init__(self) -> None:
        self.error = ""
        self._landmarker = None
        self._closed = False
        self._blinked = False
        self._load()

    @property
    def available(self) -> bool:
        return self._landmarker is not None

    @property
    def latched(self) -> bool:
        return self._blinked

    def reset(self) -> None:
        self._closed = False
        self._blinked = False

    def update(self, frame) -> bool:
        if self._blinked:
            return True
        ear = self._eye_aspect(frame)
        if ear is None:
            return False
        if ear < _CLOSED:
            self._closed = True
        elif self._closed and ear > _OPEN:
            self._blinked = True
            self._closed = False
        return self._blinked

    def _load(self) -> None:
        path = model_path(LANDMARKER_NAME)
        if not path.exists():
            self.error = "Blink model is missing. Run install.ps1."
            return
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core import base_options as base_options_lib

            options = vision.FaceLandmarkerOptions(
                base_options=base_options_lib.BaseOptions(model_asset_path=str(path)),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
            )
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
            self.error = ""
        except Exception as exc:
            self._landmarker = None
            self.error = "Blink detection could not start."
            from app.logging_setup import setup

            setup().info("blink detector unavailable: %s", exc)

    def _eye_aspect(self, frame) -> float | None:
        if self._landmarker is None or frame is None:
            return None
        import mediapipe as mp

        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(image)
        if not result.face_landmarks:
            return None
        landmarks = result.face_landmarks[0]
        height, width = frame.shape[:2]
        ratios = []
        for indices in (_RIGHT_EYE, _LEFT_EYE):
            ratio = _aspect(landmarks, indices, width, height)
            if ratio is not None:
                ratios.append(ratio)
        if not ratios:
            return None
        return sum(ratios) / len(ratios)


def _aspect(landmarks, indices, width: int, height: int) -> float | None:
    if max(indices) >= len(landmarks):
        return None
    points = [(landmarks[i].x * width, landmarks[i].y * height) for i in indices]

    def dist(a, b) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    horizontal = dist(points[0], points[3])
    if horizontal < 1.0:
        return None
    vertical = dist(points[1], points[5]) + dist(points[2], points[4])
    return vertical / (2.0 * horizontal)
