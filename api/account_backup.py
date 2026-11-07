"""Back up the account database, check a backup, and restore one.

    python -m api.account_backup backup  /app/outputs/backups/accounts-2026-11-05.sqlite3
    python -m api.account_backup verify  <file>
    python -m api.account_backup restore <file> --replace-live

Every account lives in one SQLite file (ACCOUNTS_DB). If that file is lost or
damaged, every person's sign-in is gone with it, and nothing in the product
can bring it back. Assessments are regenerable at a cost; accounts are not.
This module is the smallest thing that makes that file recoverable, and
tests/test_account_backup.py is the drill that proves a backup made by it can
actually be restored.

Backup copies the live file through SQLite's own backup interface, so it is a
consistent snapshot even while the service is writing, which a plain file
copy is not. The copy is checked before it is given its final name, and an
existing file is never overwritten: a backup that silently replaced
yesterday's would be one bad day away from being the only copy.

Restore refuses unless told to replace the live database. Before it changes
anything it sets the current file aside, damaged or not, so a restore from
the wrong backup can itself be undone. Afterwards every session and every
sign-in lockout is cleared: a backup is a picture of the past, and sessions
that were ended since it was taken must not come back to life. Everyone signs
in again with the password they had when the backup was made.

What a restore cannot give back: accounts created, passwords changed and
accounts deleted after the backup was taken. A deleted account returns, and
its assessments do not.

The backup file holds password hashes and session token hashes. Treat it as
a secret: it is written readable by its owner only, and it belongs somewhere
other than the volume it protects. A copy on the same volume survives a bad
change or a deleted file, not the loss of the volume.

The service also takes a backup by itself, once a day unless told otherwise,
and keeps the newest fourteen (`run_schedule`, called from the maintenance
loop). A backup that depends on someone remembering to take it is taken
least when it is needed most. These are the same checked snapshots, written
beside the database, so everything above about the same volume applies to
them: they are for a bad change or a deleted file. `list` shows them.

A scheduled backup keeps what was true on its day. An account deleted today
is still in yesterday's backup until that backup ages out, which the privacy
page states with the number of days from this module.
"""
from __future__ import annotations

import argparse
import calendar
import contextlib
import hashlib
import math
import os
import re
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from api import accounts

_TABLES = ("users", "sessions", "login_throttle")
_LOCK_WAIT_SECONDS = 30


class BackupError(Exception):
    """A refusal the operator can read. Nothing was changed unless it says so."""


@dataclass(frozen=True)
class Inspection:
    """What a database file holds, counted through SQLite, not guessed from bytes."""

    path: Path
    accounts: int
    sessions: int
    size: int
    sha256: str


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=_LOCK_WAIT_SECONDS)


def examine(path: Path) -> Inspection:
    """Open `path` read-only and confirm it is a whole account database."""
    if not path.is_file():
        raise BackupError(f"No file at {path}.")
    try:
        with contextlib.closing(_read_only(path)) as db:
            verdict = [row[0] for row in db.execute("PRAGMA integrity_check")]
            if verdict != ["ok"]:
                raise BackupError(f"{path} fails SQLite's integrity check: {'; '.join(map(str, verdict))[:300]}")
            present = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            missing = [name for name in _TABLES if name not in present]
            if missing:
                raise BackupError(f"{path} is not an account database: no table {', '.join(missing)}.")
            unhashed = db.execute("SELECT COUNT(*) FROM users WHERE password_hash NOT LIKE 'scrypt$%'").fetchone()[0]
            if unhashed:
                raise BackupError(f"{path} holds {unhashed} account(s) without a recognisable password hash.")
            users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    except sqlite3.Error as exc:
        raise BackupError(f"{path} cannot be read as a database: {exc}") from None
    return Inspection(path, users, sessions, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


def _live() -> Path:
    path = accounts.database_path()
    if path is None:
        raise BackupError("Accounts are not enabled here: ACCOUNTS_DB is not set.")
    return path


def _copy(source: Path, destination: Path) -> None:
    """Copy one database into another through SQLite, never byte by byte."""
    with contextlib.closing(_read_only(source)) as src, \
            contextlib.closing(sqlite3.connect(str(destination), timeout=_LOCK_WAIT_SECONDS)) as dst:
        src.backup(dst)


def _owner_only(path: Path) -> None:
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def backup(destination: Path) -> Inspection:
    """Write a checked snapshot of the live database to a new file."""
    live = _live()
    if not live.is_file():
        raise BackupError(f"No account database at {live}. Run this in the service's own shell.")
    if destination.exists() or destination.is_symlink():
        raise BackupError(f"{destination} already exists. A backup never overwrites a file; choose a new name.")
    if destination.resolve() == live.resolve():
        raise BackupError("The destination is the live database.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    partial.unlink(missing_ok=True)
    try:
        _copy(live, partial)
        _owner_only(partial)
        examine(partial)
        os.replace(partial, destination)
    except (sqlite3.Error, OSError) as exc:
        raise BackupError(f"Backup failed and nothing was kept: {exc}") from None
    finally:
        partial.unlink(missing_ok=True)
    return examine(destination)


@dataclass(frozen=True)
class Restored:
    live: Inspection
    set_aside: Path | None
    sessions_ended: int


def _match_directory_owner(path: Path) -> None:
    """A file this command created must be writable by the service.

    In the container the operator's shell is root and the service is not.
    The directory is already owned by the service user, so the file takes
    the directory's owner. Where the platform has no such call, nothing to do.
    """
    if hasattr(os, "chown"):
        parent = path.parent.stat()
        with contextlib.suppress(OSError):
            os.chown(path, parent.st_uid, parent.st_gid)


def restore(source: Path, *, now: float | None = None) -> Restored:
    """Replace the live database with a checked backup.

    The current file is set aside first, whatever state it is in. Then the
    backup is copied in through SQLite; if the current file is too damaged
    to be written into, it is removed (its copy is already safe) and the
    backup is copied into a fresh file. Sessions and lockouts are cleared.
    """
    checked = examine(source)
    live = _live()
    if live.exists() and source.resolve() == live.resolve():
        raise BackupError("The backup is the live database.")
    live.parent.mkdir(parents=True, exist_ok=True)
    set_aside = None
    created = not live.exists()
    if not created:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
        set_aside = live.with_name(f"{live.name}.before-restore-{stamp}")
        # Undoing a restore straight away is a second restore in the same
        # second; the earlier set-aside file is the one thing not to lose.
        attempt = 1
        while set_aside.exists():
            attempt += 1
            set_aside = live.with_name(f"{live.name}.before-restore-{stamp}-{attempt}")
        try:
            # Bytes, not the backup interface: the file may be too damaged to open.
            shutil.copy2(live, set_aside)
            _owner_only(set_aside)
        except OSError as exc:
            raise BackupError(f"Could not set the current database aside, so nothing was changed: {exc}") from None
    try:
        try:
            _copy(source, live)
        except sqlite3.DatabaseError:
            for stale in (live, live.with_name(live.name + "-journal"), live.with_name(live.name + "-wal"),
                          live.with_name(live.name + "-shm")):
                stale.unlink(missing_ok=True)
            created = True
            _copy(source, live)
        with contextlib.closing(sqlite3.connect(str(live), timeout=_LOCK_WAIT_SECONDS)) as db, db:
            ended = db.execute("DELETE FROM sessions").rowcount
            db.execute("DELETE FROM login_throttle")
    except (sqlite3.Error, OSError) as exc:
        kept = f" The previous file is at {set_aside}." if set_aside else ""
        raise BackupError(f"Restore failed part-way: {exc}.{kept}") from None
    if created:
        _match_directory_owner(live)
    after = examine(live)
    if after.accounts != checked.accounts:
        raise BackupError(f"Restored {after.accounts} account(s) where the backup holds {checked.accounts}. "
                          f"The previous file is at {set_aside}.")
    return Restored(after, set_aside, ended)


# ── Scheduled backups ───────────────────────────────────────────────────────

# The name carries the time, in UTC. A file's own timestamp changes when it is
# copied or restored; its name does not.
_SCHEDULED = re.compile(r"accounts-(\d{8}T\d{6}Z)\.sqlite3")
_SCHEDULE_DIRECTORY = "_account_backups"   # not a run: run directories are matched by their own shape


def _setting(name: str, default: float, *, low: float) -> float:
    try:
        value = float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return value if math.isfinite(value) and value >= low else default


def schedule_hours() -> float:
    """Hours between scheduled backups. 0 turns the schedule off; default 24."""
    return _setting("ACCOUNTS_BACKUP_HOURS", 24, low=0)


def schedule_keep() -> int:
    """How many scheduled backups are kept. At least one; default 14."""
    return int(_setting("ACCOUNTS_BACKUP_KEEP", 14, low=1))


def schedule_directory() -> Path | None:
    """Where scheduled backups go: ACCOUNTS_BACKUP_DIR, or beside the database."""
    live = accounts.database_path()
    if live is None:
        return None
    chosen = os.getenv("ACCOUNTS_BACKUP_DIR", "").strip()
    return Path(chosen) if chosen else live.parent / _SCHEDULE_DIRECTORY


def kept_days() -> int | None:
    """How long a deleted account stays in a scheduled backup, in whole days.

    None when nothing is scheduled. The privacy page states this number, so
    it is computed here, from the two settings that decide it.
    """
    if accounts.database_path() is None or schedule_hours() <= 0:
        return None
    return math.ceil(schedule_hours() * schedule_keep() / 24)


def _taken_at(path: Path) -> float | None:
    match = _SCHEDULED.fullmatch(path.name)
    if match is None:
        return None
    try:
        return float(calendar.timegm(time.strptime(match[1], "%Y%m%dT%H%M%SZ")))
    except (ValueError, OverflowError):
        return None


def taken_at(path: Path) -> int | None:
    """When a scheduled backup was taken, from its name; None for any other file."""
    moment = _taken_at(path)
    return None if moment is None else int(moment)


def scheduled_backups() -> list[Path]:
    """The scheduled backups on disk, oldest first. Only files this module named."""
    directory = schedule_directory()
    if directory is None or not directory.is_dir():
        return []
    return sorted((path for path in directory.iterdir() if path.is_file() and _taken_at(path) is not None),
                  key=lambda path: path.name)


def run_schedule(now: float | None = None) -> int:
    """Take a scheduled backup if one is due, then let the oldest go.

    Called every half minute by the maintenance loop; nearly always it looks
    at one directory and returns 0. Whether a backup is due is read from the
    newest file's name, so a restart neither forgets the last backup nor takes
    an extra one.

    Old backups are removed only after a new one has been written and
    checked. A day on which the backup fails therefore costs nothing that was
    already safe, and the failure is the maintenance stage's failure, which
    /health shows. Files with any other name in the directory are never
    touched: an operator's own backup is not this schedule's to delete.

    Returns how many backups were written: 0 or 1.
    """
    hours = schedule_hours()
    live = accounts.database_path()
    directory = schedule_directory()
    if hours <= 0 or live is None or directory is None or not live.is_file():
        return 0
    moment = time.time() if now is None else now
    existing = scheduled_backups()
    if existing:
        newest = _taken_at(existing[-1])
        if newest is not None and moment - newest < hours * 3600:
            return 0
    backup(directory / time.strftime("accounts-%Y%m%dT%H%M%SZ.sqlite3", time.gmtime(moment)))
    for old in scheduled_backups()[:-schedule_keep()]:
        with contextlib.suppress(OSError):
            old.unlink()
    return 1


def _describe(found: Inspection) -> str:
    return (f"{found.accounts} account(s), {found.sessions} session(s), {found.size:,} bytes, "
            f"sha256 {found.sha256}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m api.account_backup",
        description="Back up, check and restore the account database (ACCOUNTS_DB).")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("backup", help="Write a checked snapshot of the live database to a new file.")
    make.add_argument("destination", type=Path)
    check = commands.add_parser("verify", help="Check that a file is a whole account database. Changes nothing.")
    check.add_argument("file", type=Path)
    put = commands.add_parser("restore", help="Replace the live database with a backup; everyone signs in again.")
    put.add_argument("file", type=Path)
    put.add_argument("--replace-live", action="store_true",
                     help="Required. Says you mean to replace every account with the backup's.")
    commands.add_parser("list", help="Show the backups the service has taken by itself.")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            written = backup(args.destination)
            print(f"Backup written: {args.destination}")
            print(_describe(written))
            print("It holds password hashes. Keep it off the volume it protects, readable by you only.")
        elif args.command == "list":
            _live()
            hours, found = schedule_hours(), scheduled_backups()
            print(f"Scheduled backups in {schedule_directory()}: "
                  + (f"every {hours:g} hours, newest {schedule_keep()} kept." if hours > 0 else "the schedule is off."))
            for path in found:
                print(f"  {path.name}  {_describe(examine(path))}")
            if not found:
                print("  none yet")
        elif args.command == "verify":
            print(f"{args.file} is a whole account database: {_describe(examine(args.file))}")
        else:
            if not args.replace_live:
                found = examine(args.file)
                print(f"Not restored. {args.file} holds {found.accounts} account(s). Restoring replaces every "
                      "account in the live database with these and signs everyone out; accounts created since "
                      "the backup are lost. Run again with --replace-live to do it.", file=sys.stderr)
                return 2
            done = restore(args.file)
            print(f"Restored: {_describe(done.live)}")
            if done.set_aside:
                print(f"The previous database was set aside at {done.set_aside}. Delete it once the restore is confirmed.")
            print(f"Sessions ended: {done.sessions_ended}. Everyone signs in again with the password they had "
                  "when the backup was made.")
    except BackupError as exc:
        print(f"{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
