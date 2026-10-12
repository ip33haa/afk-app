"""Password blob and pipe message layout. These tests never use a real Windows password."""

import struct
import tempfile
import unittest
from pathlib import Path

from app.pipe_protocol import MAGIC, TYPE_UNLOCK, build_unlock, parse_challenge, parse_result
from app.secure_store import SecureStore, pack_secret, protect, unpack_secret, unprotect, wipe


class PipeLayoutTests(unittest.TestCase):
    def test_unlock_message_matches_the_provider_layout(self):
        nonce = bytes(range(32))
        message = build_unlock(nonce, "A", "B", "c".encode("utf-16-le"))
        self.assertEqual(struct.unpack_from("<I", message, 0)[0], MAGIC)
        self.assertEqual(struct.unpack_from("<I", message, 4)[0], TYPE_UNLOCK)
        self.assertEqual(message[8:40], nonce)
        user_len = struct.unpack_from("<I", message, 40)[0]
        self.assertEqual(user_len, len("A".encode("utf-16-le")))
        self.assertEqual(bytes(message[44 : 44 + user_len]), "A".encode("utf-16-le"))

    def test_challenge_and_result_round_trip(self):
        nonce = bytes(range(32))
        challenge = struct.pack("<II", MAGIC, 1) + nonce
        self.assertEqual(parse_challenge(challenge), nonce)
        self.assertEqual(parse_result(struct.pack("<III", MAGIC, 3, 0)), 0)
        self.assertEqual(parse_result(struct.pack("<III", MAGIC, 3, 1)), 1)

    def test_challenge_rejects_the_wrong_type(self):
        with self.assertRaises(ValueError):
            parse_challenge(struct.pack("<II", MAGIC, 2) + bytes(32))


class SecretStoreTests(unittest.TestCase):
    def test_pack_round_trip_keeps_the_password_bytes(self):
        username, domain, password = unpack_secret(pack_secret("philip", "WORK", "correct-horse"))
        self.assertEqual(username, "philip")
        self.assertEqual(domain, "WORK")
        self.assertEqual(bytes(password), "correct-horse".encode("utf-16-le"))
        wipe(password)

    def test_dpapi_round_trip(self):
        blob = protect(pack_secret("philip", "WORK", "correct-horse"))
        username, domain, password = unpack_secret(unprotect(blob))
        self.assertEqual((username, domain), ("philip", "WORK"))
        self.assertEqual(bytes(password), "correct-horse".encode("utf-16-le"))
        wipe(password)

    def test_corrupted_blob_does_not_decrypt(self):
        raw = bytearray(protect(pack_secret("philip", "WORK", "correct-horse")))
        raw[-1] ^= 0xFF
        with self.assertRaises(OSError):
            unprotect(bytes(raw))

    def test_save_rejects_a_password_windows_would_refuse(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SecureStore(Path(folder), logon=lambda user, domain, password: False)
            with self.assertRaises(ValueError):
                store.save("not-the-password")
            self.assertFalse(store.has_secret())

    def test_save_keeps_the_account_windows_accepted(self):
        def logon(user, domain, password):
            return password == "correct-horse" and bool(user) and bool(domain)

        with tempfile.TemporaryDirectory() as folder:
            store = SecureStore(Path(folder), logon=logon)
            store.save("correct-horse")
            username, domain, password = store.load()
            try:
                self.assertEqual(bytes(password), "correct-horse".encode("utf-16-le"))
                self.assertTrue(username)
                self.assertTrue(domain)
            finally:
                wipe(password)


if __name__ == "__main__":
    unittest.main()
