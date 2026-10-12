"""Camera models and the live session probe. This does not lock the PC."""

import unittest

import numpy as np

from app.face import FaceEngine
from app.liveness import BlinkDetector
from app.session import SessionMonitor, probe_locked


class ModelTests(unittest.TestCase):
    def test_blank_frame_is_not_a_face(self):
        engine = FaceEngine()
        self.assertTrue(engine.ready, engine.error)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertIsNone(engine.embed(frame))
        matched, score = engine.matches(frame)
        self.assertFalse(matched)
        self.assertEqual(score, 0.0)

    def test_blink_detector_loads(self):
        detector = BlinkDetector()
        self.assertTrue(detector.available, detector.error)


class SessionProbeTests(unittest.TestCase):
    def test_this_session_is_not_reported_locked(self):
        self.assertIs(probe_locked(), False)

    def test_monitor_starts_unlocked_and_does_not_lock(self):
        monitor = SessionMonitor()
        monitor.start()
        try:
            self.assertFalse(monitor.is_locked())
        finally:
            monitor.stop()


if __name__ == "__main__":
    unittest.main()
