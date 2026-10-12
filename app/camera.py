"""Webcam capture at about five frames per second."""

from __future__ import annotations

import threading
import time

import cv2


class CameraService:
    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.error = ""
        self._latest = None
        self._guard = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="afk-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        with self._guard:
            self._latest = None

    def reopen(self, index: int) -> None:
        self.index = index

    def latest(self):
        with self._guard:
            if self._latest is None:
                return None
            return self._latest.copy()

    def _run(self) -> None:
        cap = None
        opened = None
        while not self._stop.is_set():
            if cap is None or opened != self.index:
                if cap is not None:
                    cap.release()
                cap = _open_capture(self.index)
                opened = self.index
                if cap is None:
                    self.error = "Camera not available"
                    with self._guard:
                        self._latest = None
                    self._stop.wait(1.0)
                    continue
                self.error = ""
            ok, frame = cap.read()
            if not ok or frame is None:
                cap.release()
                cap = None
                self.error = "Camera not available"
                self._stop.wait(0.5)
                continue
            with self._guard:
                self._latest = frame
            self._stop.wait(0.2)
        if cap is not None:
            cap.release()


def _open_capture(index: int):
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap
    return None
