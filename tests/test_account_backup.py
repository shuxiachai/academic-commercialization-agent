"""The drill: a backup of the account database can actually be restored.

A backup nobody has restored is a hope, not a backup. Each test here loses
the live database in a different way and then signs in from the restored
one, which is the only outcome that matters to the people whose accounts are
in it. The rest pins what must not happen: a backup overwriting another, a
restore from a damaged file, a restore that cannot itself be undone, and old
sessions coming back to life.
"""
from __future__ import annotations

import contextlib
import io
import os
import sqlite3
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from api import account_backup, accounts

ALICE, BOB, CAROL = "alice@example.com", "bob@example.com", "carol@example.com"
PASSWORD = {ALICE: "alice's long password", BOB: "bob's long password", CAROL: "carol's long password"}


def _run(*argv: object) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = account_backup.main([str(arg) for arg in argv])
    return code, out.getvalue(), err.getvalue()


class _Volume(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.live = self.root / "outputs" / "accounts.sqlite3"
        self.copy = self.root / "offsite" / "accounts-backup.sqlite3"
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(self.live)})
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS"):
            os.environ.pop(name, None)
        for email in (ALICE, BOB):
            accounts.register(email, PASSWORD[email])
        self.alice_session, _ = accounts.login(ALICE, PASSWORD[ALICE])

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def _can_sign_in(self, email: str) -> bool:
        try:
            token, user = accounts.login(email, PASSWORD[email])
        except accounts.AccountError:
            return False
        return user.email == email and accounts.session_user(token) is not None

    def _backup(self) -> None:
        code, out, err = _run("backup", self.copy)
        self.assertEqual((code, err), (0, ""), out)


class DrillTests(_Volume):
    def test_the_volume_is_lost_and_everyone_can_sign_in_from_the_backup(self):
        self._backup()
        self.live.unlink()
        self.assertFalse(self.live.exists())
        code, out, err = _run("restore", self.copy, "--replace-live")
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("Restored: 2 account(s), 0 session(s)", out)
        self.assertNotIn("set aside", out)
        self.assertTrue(self._can_sign_in(ALICE))
        self.assertTrue(self._can_sign_in(BOB))
        # The restored file is a working database for the service: it can write.
        accounts.register(CAROL, PASSWORD[CAROL])
        self.assertTrue(self._can_sign_in(CAROL))

    def test_a_file_the_restore_creates_is_handed_to_the_directory_owner(self):
        # In the container the operator's shell is root and the service is
        # not; a root-owned database would be one the service cannot write.
        self._backup()
        self.live.unlink()
        with patch.object(account_backup.os, "chown", create=True) as chown:
            self.assertEqual(_run("restore", self.copy, "--replace-live")[0], 0)
        directory = self.live.parent.stat()
        chown.assert_called_once_with(self.live, directory.st_uid, directory.st_gid)
        # Restoring over a file that exists keeps that file's owner: nothing to hand over.
        with patch.object(account_backup.os, "chown", create=True) as chown:
            self.assertEqual(_run("restore", self.copy, "--replace-live")[0], 0)
        chown.assert_not_called()

    def test_the_file_is_damaged_and_the_backup_replaces_it(self):
        self._backup()
        damaged = bytearray(self.live.read_bytes())
        damaged[:64] = b"\x00" * 64
        for offset in range(1024, len(damaged), 512):
            damaged[offset:offset + 64] = b"\xff" * 64
        self.live.write_bytes(bytes(damaged))
        with self.assertRaises(sqlite3.DatabaseError):
            accounts.login(ALICE, PASSWORD[ALICE])
        code, out, err = _run("restore", self.copy, "--replace-live")
        self.assertEqual((code, err), (0, ""), out)
        self.assertTrue(self._can_sign_in(ALICE))
        self.assertTrue(self._can_sign_in(BOB))
        # Even a damaged file is kept, byte for byte, until the restore is confirmed.
        aside = list(self.live.parent.glob("accounts.sqlite3.before-restore-*"))
        self.assertEqual(len(aside), 1)
        self.assertEqual(aside[0].read_bytes(), bytes(damaged))
        self.assertIn(str(aside[0]), out)

    def test_a_bad_change_is_rolled_back_and_the_loss_window_is_what_the_docs_say(self):
        self._backup()
        # After the backup: one account is created, one password is changed, one account is deleted.
        accounts.register(CAROL, PASSWORD[CAROL])
        _, bob = accounts.login(BOB, PASSWORD[BOB])
        accounts.change_password(bob, PASSWORD[BOB], "bob's newer password")
        _, alice = accounts.login(ALICE, PASSWORD[ALICE])
        accounts.delete_account(alice, PASSWORD[ALICE])
        code, out, err = _run("restore", self.copy, "--replace-live")
        self.assertEqual((code, err), (0, ""), out)
        self.assertFalse(self._can_sign_in(CAROL), "An account created after the backup is not in it")
        self.assertTrue(self._can_sign_in(BOB), "The password is the one from the day of the backup")
        self.assertTrue(self._can_sign_in(ALICE), "A deleted account returns")
        # And the restore can itself be undone from the file it set aside.
        aside = next(self.live.parent.glob("accounts.sqlite3.before-restore-*"))
        self.assertEqual(account_backup.examine(aside).accounts, 2)
        code, _, err = _run("restore", aside, "--replace-live")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(self._can_sign_in(CAROL))
        self.assertFalse(self._can_sign_in(ALICE))
        # Undoing did not cost the first set-aside file: both are still there.
        self.assertEqual(len(list(self.live.parent.glob("accounts.sqlite3.before-restore-*"))), 2)
        self.assertEqual(account_backup.examine(aside).accounts, 2)

    def test_sessions_and_lockouts_from_the_past_do_not_come_back(self):
        for _ in range(accounts.LOCKOUT_FAILURES):
            with self.assertRaises(accounts.AccountError):
                accounts.login(BOB, "a wrong guess 123", client="203.0.113.9")
        self._backup()
        self.assertEqual(account_backup.examine(self.copy).sessions, 1)
        # Alice signs out after the backup; that session must stay ended.
        self.assertTrue(accounts.logout(self.alice_session))
        code, out, _ = _run("restore", self.copy, "--replace-live")
        self.assertEqual(code, 0)
        self.assertIn("Sessions ended: 1.", out)
        self.assertIsNone(accounts.session_user(self.alice_session))
        token, _ = accounts.login(BOB, PASSWORD[BOB], client="203.0.113.9")
        self.assertIsNotNone(accounts.session_user(token))

    def test_a_backup_taken_while_the_service_is_writing_is_whole(self):
        stop = threading.Event()
        failures: list[BaseException] = []

        def keep_writing():
            index = 0
            while not stop.is_set():
                try:
                    accounts.register(f"writer{index}@example.com", "a writer's long password")
                except BaseException as exc:  # noqa: BLE001 - reported by the assertion below
                    failures.append(exc)
                    return
                index += 1

        writer = threading.Thread(target=keep_writing)
        writer.start()
        try:
            snapshots = []
            for index in range(5):
                target = self.copy.with_name(f"during-{index}.sqlite3")
                self.assertEqual(_run("backup", target)[0], 0)
                snapshots.append(account_backup.examine(target))
        finally:
            stop.set()
            writer.join(30)
        self.assertEqual(failures, [])
        counts = [snapshot.accounts for snapshot in snapshots]
        self.assertEqual(counts, sorted(counts))
        self.assertGreaterEqual(counts[0], 2)


class RefusalTests(_Volume):
    def test_a_backup_never_overwrites_a_file(self):
        self._backup()
        before = self.copy.read_bytes()
        accounts.register(CAROL, PASSWORD[CAROL])
        code, out, err = _run("backup", self.copy)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("already exists", err)
        self.assertEqual(self.copy.read_bytes(), before)
        self.assertEqual(_run("backup", self.live)[0], 2)
        self.assertEqual(list(self.copy.parent.glob("*.partial")), [])

    def test_restore_does_nothing_until_it_is_told_to_replace_the_live_database(self):
        self._backup()
        accounts.register(CAROL, PASSWORD[CAROL])
        before = self.live.read_bytes()
        code, out, err = _run("restore", self.copy)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--replace-live", err)
        self.assertIn("2 account(s)", err)
        self.assertEqual(self.live.read_bytes(), before)
        self.assertEqual(list(self.live.parent.glob("*.before-restore-*")), [])

    def test_a_damaged_or_foreign_file_is_never_restored(self):
        self._backup()
        whole = self.copy.read_bytes()
        truncated = self.root / "truncated.sqlite3"
        truncated.write_bytes(whole[: len(whole) // 2])
        garbage = self.root / "garbage.sqlite3"
        garbage.write_bytes(b"not a database at all" * 100)
        other = self.root / "other.sqlite3"
        with contextlib.closing(sqlite3.connect(other)) as db, db:
            db.execute("CREATE TABLE notes (body TEXT)")
        plaintext = self.root / "plaintext.sqlite3"
        plaintext.write_bytes(whole)
        with contextlib.closing(sqlite3.connect(plaintext)) as db, db:
            db.execute("UPDATE users SET password_hash = 'hunter2' WHERE email = ?", (ALICE,))
        before = self.live.read_bytes()
        for bad in (truncated, garbage, other, plaintext, self.root / "missing.sqlite3"):
            with self.subTest(file=bad.name):
                self.assertEqual(_run("verify", bad)[0], 2)
                code, out, err = _run("restore", bad, "--replace-live")
                self.assertEqual((code, out), (2, ""), err)
                self.assertEqual(self.live.read_bytes(), before)
        self.assertEqual(list(self.live.parent.glob("*.before-restore-*")), [])
        self.assertTrue(accounts.session_user(self.alice_session) is not None)

    def test_verify_reports_what_a_backup_holds_and_changes_nothing(self):
        self._backup()
        before = (self.copy.read_bytes(), self.live.read_bytes())
        code, out, err = _run("verify", self.copy)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("2 account(s), 1 session(s)", out)
        self.assertIn(account_backup.examine(self.copy).sha256, out)
        self.assertEqual((self.copy.read_bytes(), self.live.read_bytes()), before)

    def test_the_backup_is_written_for_its_owner_only_and_names_no_password(self):
        code, out, _ = _run("backup", self.copy)
        self.assertEqual(code, 0)
        self.assertIn("password hashes", out)
        for secret in PASSWORD.values():
            self.assertNotIn(secret.encode(), self.copy.read_bytes())
            self.assertNotIn(secret, out)
        self.assertNotIn(self.alice_session.encode(), self.copy.read_bytes())
        if os.name == "posix":
            self.assertEqual(self.copy.stat().st_mode & 0o777, 0o600)

    def test_without_accounts_or_without_a_database_nothing_is_created(self):
        missing = self.root / "nowhere" / "accounts.sqlite3"
        with patch.dict("os.environ", {"ACCOUNTS_DB": str(missing)}):
            code, _, err = _run("backup", self.root / "new.sqlite3")
        self.assertEqual(code, 2)
        self.assertIn("No account database", err)
        self.assertFalse(missing.parent.exists())
        self.assertFalse((self.root / "new.sqlite3").exists())
        self._backup()
        os.environ.pop("ACCOUNTS_DB")
        for argv in (("backup", self.root / "new.sqlite3"), ("restore", self.copy, "--replace-live")):
            with self.subTest(command=argv[0]):
                code, _, err = _run(*argv)
                self.assertEqual(code, 2)
                self.assertIn("ACCOUNTS_DB is not set", err)

    def test_a_restore_that_cannot_set_the_current_file_aside_changes_nothing(self):
        self._backup()
        accounts.register(CAROL, PASSWORD[CAROL])
        before = self.live.read_bytes()
        with patch.object(account_backup.shutil, "copy2", side_effect=OSError("disk full")):
            code, out, err = _run("restore", self.copy, "--replace-live")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("nothing was changed", err)
        self.assertEqual(self.live.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
