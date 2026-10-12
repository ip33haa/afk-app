"""Lock-screen key filter and PIN check. These tests do not cover the desktop."""

import tempfile
import unittest
from pathlib import Path

from app.screen_lock import VK_APPS, VK_ESCAPE, VK_F4, VK_LWIN, VK_TAB, block_lock_key
from app.anime import LINES
from app.verses import VERSES, lock_screen_text, random_verse
from app.secure_store import SecureStore
from app.wallpaper import lock_image_path


class VerseTests(unittest.TestCase):
    def test_a_lock_message_is_a_known_verse(self):
        shown = {f"“{verse.text}”\n\n{verse.reference}" for verse in VERSES}
        self.assertIn(random_verse(), shown)
        self.assertGreater(len(VERSES), 10)

    def test_the_normal_lock_screen_uses_an_anime_line(self):
        shown = {f"“{line.text}”\n\n{line.speaker}" for line in LINES}
        self.assertIn(lock_screen_text(show_verse=False, require_blink=False), shown)
        self.assertIn(lock_screen_text(show_verse=False, require_blink=True), shown)


class WallpaperTests(unittest.TestCase):
    def test_windows_wallpaper_path_is_a_file_when_present(self):
        path = lock_image_path()
        if path is not None:
            self.assertTrue(path.is_file())


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
