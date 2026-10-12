"""Presence decisions: stay unlocked, lock after leaving, unlock on return."""

import unittest

from app.presence import PresenceEngine


def tick(engine, present, blinked, locked, now):
    return engine.update(
        enrolled_face_present=present,
        blinked=blinked,
        session_locked=locked,
        now=now,
    )


class PresenceTests(unittest.TestCase):
    def test_staying_in_view_does_not_lock(self):
        engine = PresenceEngine(grace_seconds=8)
        for second in range(0, 30):
            result = tick(engine, True, False, False, second)
            self.assertIsNone(result.action)
            self.assertEqual(engine.state, "armed")

    def test_leaving_locks_once_after_the_grace_period(self):
        engine = PresenceEngine(grace_seconds=8)
        tick(engine, True, False, False, 0)
        tick(engine, False, False, False, 1)
        self.assertIsNone(tick(engine, False, False, False, 8.9).action)
        result = tick(engine, False, False, False, 9.0)
        self.assertEqual(result.action, "lock")
        self.assertEqual(engine.state, "locking")
        self.assertIsNone(tick(engine, False, False, False, 9.5).action)
        tick(engine, False, False, True, 9.6)
        self.assertEqual(engine.state, "watching_locked")

    def test_coming_back_before_the_grace_period_cancels_the_lock(self):
        engine = PresenceEngine(grace_seconds=8)
        tick(engine, True, False, False, 0)
        tick(engine, False, False, False, 1)
        tick(engine, True, False, False, 5)
        result = tick(engine, True, False, False, 20)
        self.assertIsNone(result.action)
        self.assertEqual(engine.state, "armed")

    def test_a_different_face_counts_as_away(self):
        engine = PresenceEngine(grace_seconds=8)
        tick(engine, True, False, False, 0)
        tick(engine, False, False, False, 1)
        result = tick(engine, False, False, False, 9)
        self.assertEqual(result.action, "lock")

    def test_manual_lock_starts_watching_without_another_lock(self):
        engine = PresenceEngine()
        tick(engine, True, False, False, 0)
        result = tick(engine, True, False, True, 1)
        self.assertIsNone(result.action)
        self.assertEqual(engine.state, "watching_locked")

    def test_unlock_waits_for_a_steady_match_and_a_blink(self):
        engine = PresenceEngine(match_hold_seconds=1, require_blink=True)
        engine.state = "watching_locked"
        self.assertIsNone(tick(engine, True, False, True, 0).action)
        self.assertIsNone(tick(engine, True, False, True, 1).action)
        result = tick(engine, True, True, True, 1.2)
        self.assertEqual(result.action, "unlock")
        self.assertEqual(engine.state, "unlocking")

    def test_unlock_without_blink_when_that_check_is_off(self):
        engine = PresenceEngine(match_hold_seconds=1, require_blink=False)
        engine.state = "watching_locked"
        tick(engine, True, False, True, 0)
        result = tick(engine, True, False, True, 1)
        self.assertEqual(result.action, "unlock")

    def test_accepted_unlock_is_not_sent_again_while_still_looking(self):
        engine = PresenceEngine(match_hold_seconds=1, require_blink=False)
        engine.state = "watching_locked"
        tick(engine, True, False, True, 0)
        self.assertEqual(tick(engine, True, False, True, 1).action, "unlock")
        engine.note_unlock_result("accepted", 1.1)
        self.assertIsNone(tick(engine, True, False, True, 2).action)
        self.assertEqual(engine.state, "unlocking")

    def test_rejected_unlock_waits_until_the_face_leaves_and_returns(self):
        engine = PresenceEngine(match_hold_seconds=1, require_blink=False, match_gap_seconds=0.4)
        engine.state = "watching_locked"
        tick(engine, True, False, True, 0)
        tick(engine, True, False, True, 1)
        engine.note_unlock_result("rejected", 1.1)
        self.assertIsNone(tick(engine, True, False, True, 3).action)
        tick(engine, False, False, True, 4)
        tick(engine, True, False, True, 5)
        result = tick(engine, True, False, True, 6.1)
        self.assertEqual(result.action, "unlock")

    def test_missing_pipe_retries_then_stops(self):
        engine = PresenceEngine(match_hold_seconds=1, require_blink=False)
        engine.state = "watching_locked"
        tick(engine, True, False, True, 0)
        self.assertEqual(tick(engine, True, False, True, 1).action, "unlock")
        engine.note_unlock_result("unavailable", 1)
        self.assertIsNone(tick(engine, True, False, True, 1.5).action)
        self.assertEqual(tick(engine, True, False, True, 2).action, "unlock")

    def test_cooldown_does_not_lock_immediately(self):
        engine = PresenceEngine(grace_seconds=8, cooldown_seconds=8)
        engine.state = "unlocking"
        engine._unlock_started = 0
        tick(engine, False, False, False, 1)
        self.assertEqual(engine.state, "cooldown")
        result = tick(engine, False, False, False, 2)
        self.assertIsNone(result.action)
        self.assertEqual(engine.state, "cooldown")
        tick(engine, False, False, False, 9)
        self.assertEqual(engine.state, "armed")
        self.assertIsNone(tick(engine, False, False, False, 16).action)
        self.assertEqual(tick(engine, False, False, False, 17).action, "lock")

    def test_returning_during_lock_cancels_it(self):
        engine = PresenceEngine(grace_seconds=8)
        tick(engine, True, False, False, 0)
        tick(engine, False, False, False, 1)
        tick(engine, False, False, False, 9)
        self.assertEqual(engine.state, "locking")
        tick(engine, True, False, False, 9.2)
        self.assertEqual(engine.state, "armed")


if __name__ == "__main__":
    unittest.main()
