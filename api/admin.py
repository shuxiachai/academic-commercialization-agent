"""What an admin account may see and do from the page, instead of a shell.

Every operator task so far has been a command in the deployment's own shell:
reset a password, list the backups, find out who has an account. The shell
is the right place for the operations that need it, restoring a backup above
all. It is the wrong place for the ones the operator does most, because it
is the place they reach least: on a phone, from the kitchen, when someone
has just written to say they are locked out.

api/account_admin.py says the password reset is deliberately not an HTTP
route, because a route would need a secret of its own and a secret is one
more thing to leak. That was right when there was nothing to tie a route to.
There is now: an admin account, named by the operator in
ACCOUNTS_ADMIN_EMAILS and registered with the invite code. So the routes are
tied to that, and to three more things:

  • every action re-asks the admin's own password, under the same lockout
    as a sign-in, so a session left open in a browser is not enough;
  • an admin cannot reset or disable their own account here, which would be
    either the wrong tool (change password) or a way to lock themself out;
  • each action is one line in the service log, by account id, and an email
    address never goes in a URL, where it would be written to the access log.

An admin access code (ACCESS_CODE_ADMIN) is not an admin here. It reads
every run, which is what it was for; it cannot be asked for a password, and
it answers to nobody by name.

What a reset returns is the one thing it has to: a password that is shown
once and stored only as its hash, like the command. The admin sends it to
the account's own address. The account's sessions have ended already.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from api import account_backup, accounts, runs

_LOGGER = logging.getLogger(__name__)

# 18 random bytes, 24 URL-safe characters: far above the password policy and
# short enough to read out or paste without wrapping.
_GENERATED_BYTES = 18


def generated_password() -> str:
    return secrets.token_urlsafe(_GENERATED_BYTES)


class AdminRefusal(Exception):
    """Why an action was not taken: `code` is stable, `message` is prose."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── Accounts ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AccountRow:
    id: int
    email: str
    created_at: int
    disabled: bool
    verified: bool
    admin: bool
    sessions: int
    last_seen_at: int | None
    runs: int
    # Assessments the account started on its trial and did not get back.
    trial_used: int = 0


def _runs_by_owner() -> dict[str, int]:
    """How many runs each owner tag has, from one pass over the run directories.

    A marker that cannot be read counts for nobody: this is a number on a
    page, not an authorization, and the page says when it is incomplete.
    """
    counts: dict[str, int] = {}
    for directory in runs.run_directories():
        try:
            owner = runs.owner_of(directory.name)
        except runs.OwnerMarkerUnreadable:
            continue
        if owner is not None:
            counts[owner] = counts.get(owner, 0) + 1
    return counts


def list_accounts(*, now: float | None = None) -> list[AccountRow]:
    """Every account, newest first, with what an operator asks about one.

    Sessions are the live ones: a token that has expired is not a sign-in,
    even before the next use removes its row.
    """
    stamp = int(now if now is not None else time.time())
    admins = accounts.admin_emails()
    by_owner = _runs_by_owner()
    rows = []
    for user in accounts.list_users(now=stamp):
        rows.append(AccountRow(
            id=user["id"], email=user["email"], created_at=user["created_at"], disabled=bool(user["disabled"]),
            verified=user["verified_at"] is not None, admin=user["email"] in admins, sessions=user["sessions"], last_seen_at=user["last_seen_at"],
            runs=by_owner.get(accounts.owner_tag(user["id"]), 0), trial_used=user["trial_used"],
        ))
    return rows


def _target(user_id: int, acting: accounts.User, *, verb: str) -> accounts.User:
    target = accounts.user_by_id(user_id)
    if target is None:
        raise AdminRefusal("unknown_account", "No account has this id.")
    if target.id == acting.id:
        raise AdminRefusal("own_account", f"You cannot {verb} your own account here. "
                           + ("Use Account, then change password." if verb == "reset" else
                              "Another admin, or the operator's shell, has to do that."))
    return target


def reset_password(user_id: int, acting: accounts.User, password: object, *, client: str | None = None) -> tuple[str, str, int]:
    """Give an account a new random password, as the command does.

    The admin's own password is confirmed first, under the sign-in lockout.
    Returns the account's email, the new password (the only time it exists
    in the clear) and how many of its sessions ended.
    """
    accounts.confirm_password(acting, password, client=client)
    target = _target(user_id, acting, verb="reset")
    new = generated_password()
    ended = accounts.reset_password(target.email, new)
    _LOGGER.warning("Admin account %d reset the password of account %d; %d session(s) ended.",
                    acting.id, target.id, ended)
    return target.email, new, ended


def set_disabled(user_id: int, acting: accounts.User, password: object, disabled: bool, *,
                 client: str | None = None) -> str:
    """Stop an account signing in, or let it again. Returns the account's email.

    Disabling ends its sessions at once (accounts.set_disabled). Enabling
    changes nothing else: a password reset is a separate decision.
    """
    accounts.confirm_password(acting, password, client=client)
    target = _target(user_id, acting, verb="disable" if disabled else "enable")
    accounts.set_disabled(target.email, disabled)
    _LOGGER.warning("Admin account %d %s account %d.", acting.id, "disabled" if disabled else "enabled", target.id)
    return target.email


# ── The funnel ──────────────────────────────────────────────────────────────

_RUN_STATES = ("completed", "failed", "cancelled", "timeout", "running", "unknown")


@dataclass(frozen=True)
class Funnel:
    """Of the accounts created in a window, how many got how far; and how the window's runs ended.

    Counts only: no address is in it. Each account step is a subset of
    the one before, over the accounts created in the window and not named
    as administrators. The run counts are over runs started in the
    window by anyone but an administrator, whose runs are counted apart.
    """

    window_days: int
    since: int
    accounts_created: int = 0
    accounts_verified: int = 0
    accounts_ran: int = 0
    accounts_completed: int = 0
    runs: dict[str, int] = field(default_factory=dict)
    failures: list[tuple[str, int]] = field(default_factory=list)
    trial_started: int = 0
    trial_completed: int = 0
    trial_given_back: int = 0
    admin_runs: int = 0
    #: Start of the oldest run still on the volume, of all of them: no run
    #: count reaches further back, whatever window is asked for.
    runs_kept_since: int | None = None
    #: Runs whose owner or state could not be read; in no other number.
    unreadable: int = 0


def _run_started(name: str) -> int | None:
    """Unix time a run began, from the UTC stamp its id starts with."""
    try:
        return int(datetime.strptime(name[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp())
    except ValueError:
        return None


def _trial_marker(directory: Path) -> bool | None:
    """Whether a trial run's trial was given back; None when the run was not a trial."""
    try:
        record = json.loads((directory / runs._TRIAL_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record.get("released") is True if isinstance(record, dict) else None


def funnel(days: int, *, now: float | None = None) -> Funnel:
    """The funnel over the last `days` days.

    What sign-up and a first assessment on the deployment's keys are for
    is that a newcomer reaches a finished report. The console listed
    accounts and counted runs; how many newcomers proved their address,
    started a run or finished one had to be counted by eye. This is that
    count, from what is kept: the account database and the run
    directories. A run its owner deleted, or one retention removed, is in
    no number here, which is why the oldest kept run is reported with it.
    """
    stamp = int(now if now is not None else time.time())
    since = stamp - days * 86400
    admins = accounts.admin_emails()
    everyone = accounts.list_users(now=stamp)
    admin_owners = {accounts.owner_tag(user["id"]) for user in everyone if user["email"] in admins}
    cohort = {accounts.owner_tag(user["id"]): user for user in everyone
              if user["email"] not in admins and user["created_at"] >= since}

    ran: set[str] = set()
    completed: set[str] = set()
    counts = {"started": 0, **{state: 0 for state in _RUN_STATES}}
    failures: dict[str, int] = {}
    trial_started = trial_completed = trial_given_back = admin_runs = unreadable = 0
    kept_since: int | None = None

    for directory in runs.run_directories():
        started = _run_started(directory.name)
        if started is not None and (kept_since is None or started < kept_since):
            kept_since = started
        try:
            owner = runs.owner_of(directory.name)
            state = runs.get_state(directory.name)
        except (runs.OwnerMarkerUnreadable, runs.RunNotFound, OSError, ValueError):
            unreadable += 1
            continue
        outcome = state.get("state")
        outcome = outcome if outcome in _RUN_STATES else "unknown"
        # The cohort's steps look at every kept run of a cohort account: an
        # account created inside the window cannot have run before it.
        if owner in cohort:
            ran.add(owner)
            if outcome == "completed":
                completed.add(owner)
        if started is None or started < since:
            continue
        if owner in admin_owners:
            admin_runs += 1
            continue
        counts["started"] += 1
        counts[outcome] += 1
        if outcome == "failed":
            code = state.get("error_code") or "unknown"
            failures[code] = failures.get(code, 0) + 1
        released = _trial_marker(directory)
        if released is not None:
            trial_started += 1
            trial_completed += outcome == "completed"
            trial_given_back += released

    return Funnel(
        window_days=days, since=since,
        accounts_created=len(cohort),
        accounts_verified=sum(1 for user in cohort.values() if user["verified_at"] is not None),
        accounts_ran=len(ran), accounts_completed=len(completed),
        runs=counts,
        # Most frequent first; a tie goes by the code's name, so the same runs
        # always read in the same order.
        failures=sorted(failures.items(), key=lambda item: (-item[1], item[0])),
        trial_started=trial_started, trial_completed=trial_completed, trial_given_back=trial_given_back,
        admin_runs=admin_runs, runs_kept_since=kept_since, unreadable=unreadable,
    )


# ── Backups ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BackupRow:
    name: str
    taken_at: int | None
    size: int
    accounts: int | None       # None when the file could not be verified
    problem: str | None


def list_backups() -> list[BackupRow]:
    """The scheduled backups, newest first, each opened and checked.

    What the operator wants to know is not that files exist but that they
    would restore: each is verified the way `verify` does it. One that
    fails is listed with the reason, never silently left out.
    """
    rows = []
    for path in reversed(account_backup.scheduled_backups()):
        taken = account_backup.taken_at(path)
        try:
            found = account_backup.examine(path)
            rows.append(BackupRow(path.name, taken, found.size, found.accounts, None))
        except account_backup.BackupError as exc:
            rows.append(BackupRow(path.name, taken, _size(path), None, str(exc)))
    return rows


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
