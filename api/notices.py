"""Tell an account by email when one of its assessments has ended.

Opt-in per account (`users.notify_done`, set from the Account panel), and
only on a deployment that can send mail (api/mail.py). A run takes a
quarter of an hour; the page follows it live, but nobody is obliged to keep
a tab open that long, and the result is a link that keeps.

The server learns of a run's end lazily: the worker is a separate process
that writes its terminal record and exits, and nothing in the API waits on
it. So this is a sweep, run from the maintenance loop (api/main.py) each
cycle, over the newest run directories. A marker file in the run directory
(.notice) records that the account was told, or why it was not, so a
restart neither repeats a message nor loses the fact, and an account that
turns the notice on later is not told about runs that ended before. Runs
that ended more than a day before a sweep saw them are marked without a
message: a deployment that was down for a week should not greet its return
with a week of mail, and the run page said what happened.

Only completed and failed runs are announced. A run the person cancelled is
nobody's news, and a timeout is a failure the operator is already told of.
The message carries the run's topic, which the account typed itself, and
the run's link, which is the capability; it goes to the address the account
signed up with and nowhere else.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from api import accounts, mail, runs

_LOGGER = logging.getLogger(__name__)

_MARKER = ".notice"
ANNOUNCED = ("completed", "failed")
# A run that ended longer ago than this is marked, not announced.
WINDOW = timedelta(days=1)
# Run directories older than this (by the timestamp in the id) are not even
# looked at: no run lasts that long, so nothing in them can be fresh news.
_LOOKBACK = timedelta(days=2)


def enabled() -> bool:
    """There are accounts to tell and a way to tell them."""
    return accounts.enabled() and mail.configured()


def sweep(*, now: datetime | None = None) -> list[str]:
    """Announce every newly ended run whose account asked; return the ids announced.

    Each run directory is decided once and marked, whatever the decision. A
    message that cannot be sent is not retried: the failure is logged by
    account id, mail's own state says so in /health, and the run page is
    unchanged either way.
    """
    if not enabled():
        return []
    moment = now or datetime.now(UTC)
    announced: list[str] = []
    for run_dir in runs.run_directories():
        run_id = run_dir.name
        started = _started(run_id)
        if started is not None and moment - started > _LOOKBACK:
            break
        if (run_dir / _MARKER).exists():
            continue
        try:
            owner = runs.owner_of(run_id)
        except runs.OwnerMarkerUnreadable:
            continue
        if not accounts.is_user_owner(owner):
            continue
        record = runs.terminal_record(run_id)
        if record is None:
            continue
        if record.state not in ANNOUNCED:
            _mark(run_dir, "skipped", record.state)
            continue
        if moment - record.ended_at > WINDOW:
            _mark(run_dir, "stale", record.state)
            continue
        user = accounts.user_by_id(_user_id(owner))
        if user is None or not user.notify_done:
            _mark(run_dir, "declined", record.state)
            continue
        link = f"{mail.public_url()}/run/{run_id}"
        subject, text, body = mail.run_notice_message(
            link, topic=runs.topic_of(run_id), state=record.state, minutes=record.elapsed_seconds // 60)
        try:
            mail.send(user.email, subject, text, body)
        except mail.MailError as exc:
            _mark(run_dir, "failed", record.state)
            _LOGGER.warning("Run notice for account %d about %s not sent: %s", user.id, run_id, exc)
            continue
        _mark(run_dir, "sent", record.state)
        announced.append(run_id)
    return announced


def _started(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id.split("-")[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _user_id(owner: str) -> int | None:
    try:
        return int(owner.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


def _mark(run_dir: Path, outcome: str, state: str) -> None:
    """Record the decision in the run directory; a directory that cannot be
    written is logged and left, and the next sweep decides it again."""
    try:
        (run_dir / _MARKER).write_text(
            json.dumps({"outcome": outcome, "state": state, "at": datetime.now(UTC).isoformat()}), encoding="utf-8")
    except OSError as exc:
        _LOGGER.warning("Run notice marker for %s not written: %s", run_dir.name, exc)
