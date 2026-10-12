"""Lock-screen key filter and PIN check. These tests do not cover the desktop."""

import tempfile
import unittest
from pathlib import Path

from app.screen_lock import VK_APPS, VK_ESCAPE, VK_F4, VK_LWIN, VK_TAB, block_lock_key
from app.secure_store import SecureStore


class LockKeyTests(unittest.TestCase):
    def test_shortcuts_that_leave_the_screen_are_blocked(self):
        self.assertTrue(block_lock_key(VK_LWIN, alt=False, ctrl=False))
        self.assertTrue(block_lock_key(VK_APPS, alt=False, ctrl=False))
        self.assertTrue(block_lock_key(VK_TAB, alt=True, ctrl=False))
        self.assertTrue(block_lock_key(VK_F4, alt=True, ctrl=False))
        self.assertTrue(block_lock_key(VK_ESCAPE, alt=False, ctrl=True))

    def test_pin_typing_is_not_blocked(self):
        self.assertFalse(block_lock_key(ord("A"), alt=False, ctrl=False))
        self.assertFalse(block_lock_key(ord("5"), alt=False, ctrl=False))
        self.assertFalse(block_lock_key(VK_TAB, alt=False, ctrl=False))


class PinMatchTests(unittest.TestCase):
    def test_saved_pin_matches_and_a_different_one_does_not(self):
        def logon(user, domain, password):
            return password == "correct-horse" and bool(user) and bool(domain)

        with tempfile.TemporaryDirectory() as folder:
            store = SecureStore(Path(folder), logon=logon)
            store.save("correct-horse")
            self.assertTrue(store.pin_matches("correct-horse"))
            self.assertFalse(store.pin_matches("wrong"))
            self.assertFalse(store.pin_matches(""))


if __name__ == "__main__":
    unittest.main()
