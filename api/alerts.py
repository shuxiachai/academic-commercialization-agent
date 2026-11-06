"""Tell the operator when the service needs them.

Everything this reports is already in /health or in a run's own status. The
difference is who has to act first: /health answers a person who asks, and a
backup that has been failing for a week is found by nobody who does not ask.

What is reported, and nothing else:

  • a maintenance stage that failed, again while it stays failed, and once
    more when it is back;
  • the maintenance loop itself ending, which takes the timeout watchdog
    with it;
  • a run paid for by the deployment that failed for a reason only the
    operator can remove: its key refused, its free quota used up, its account
    unbillable, its model unavailable or refusing the request.

The message goes to a WeCom (企业微信) group robot. It names stages and
failure codes, counts and the revision. It never carries a run ID, a topic,
an email address, a path or a provider's own words: a run ID opens the run,
and the group and its vendor are not parties to any assessment. The run IDs
are in the service log, which only the operator reads.

The robot's address is a secret: whoever holds it can post to the group. It
is read from ALERT_WECOM_WEBHOOK and is never logged, echoed or put in an
error. The request is built here against WeCom's own host, so a mistyped
setting cannot send alerts anywhere else; it can only be refused, and
/health then says `misconfigured`.

What this cannot report is the service being down. A process that is not
running sends nothing; that needs a monitor outside it.

    python -m api.alerts test     send one test message and say what happened
"""

from __future__ import annotations

import argparse
import http.client
import json
import logging
import math
import os
import re
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, quote, urlsplit

_LOGGER = logging.getLogger(__name__)

# WeCom's own address. It is a constant, not a setting: the setting supplies
# the robot's key and nothing else.
_HOST = "qyapi.weixin.qq.com"
_PATH = "/cgi-bin/webhook/send"
_KEY = re.compile(r"[A-Za-z0-9_-]{16,128}")
_TIMEOUT_SECONDS = 10
# WeCom refuses a text message longer than this many UTF-8 bytes.
_MAX_BYTES = 2048
_REPLY_LIMIT = 65536

# Shown beside the names /health uses, so the message can be matched to it.
_STAGES = {
    "timeouts": "超时看门狗：超时的评估不会被终止，/health/ready 会报未就绪",
    "papers": "清理过期的上传论文",
    "retention": "清理过期的评估",
    "receipts": "清理过期的收据",
    "auxiliary_usage": "清理辅助调用的用量记录",
    "account_backup": "账号数据库自动备份",
}
_FAILURES = {
    "provider_auth": "模型服务商拒绝了部署方的密钥",
    "provider_free_quota": "部署方所用模型的免费额度已用完",
    "provider_billing": "部署方的模型服务商账户无法扣费",
    "provider_model_unavailable": "部署方的密钥不能使用所设置的模型",
    "provider_request_rejected": "所设置的模型拒绝了请求",
}
LOOP_STOPPED = "maintenance:loop"


class AlertError(RuntimeError):
    """Why a message was not delivered, in words that hold no secret."""


# ── Settings ────────────────────────────────────────────────────────────────

def _webhook_key() -> str | None:
    """The robot's key, from the address WeCom shows or from the key alone.

    None when nothing usable is set. An address is accepted only if it is
    WeCom's own: anything else is a mistake, and guessing at a mistake would
    send operational messages to wherever it pointed.
    """
    value = os.getenv("ALERT_WECOM_WEBHOOK", "").strip()
    if not value:
        return None
    if "/" not in value and "?" not in value:
        return value if _KEY.fullmatch(value) else None
    try:
        parts = urlsplit(value)
        keys = parse_qs(parts.query).get("key", [])
    except ValueError:
        return None
    if (parts.scheme, parts.hostname, parts.port, parts.path) != ("https", _HOST, None, _PATH):
        return None
    if parts.username is not None or len(keys) != 1 or not _KEY.fullmatch(keys[0]):
        return None
    return keys[0]


def configured() -> str:
    """`off`, `ready`, or `misconfigured` when the setting is there but unusable."""
    if not os.getenv("ALERT_WECOM_WEBHOOK", "").strip():
        return "off"
    return "ready" if _webhook_key() else "misconfigured"


def repeat_seconds() -> float:
    """How long before a standing problem is mentioned again. Default six hours.

    The same period limits how often one kind of run failure is reported.
    Nonsense, and anything under six minutes, is the default: a robot that
    repeats itself every cycle is muted by the people it is for.
    """
    try:
        hours = float(os.getenv("ALERT_REPEAT_HOURS", "").strip() or 6)
    except ValueError:
        return 6 * 3600.0
    return hours * 3600.0 if math.isfinite(hours) and hours >= 0.1 else 6 * 3600.0


def _service() -> str:
    """Which deployment is speaking, for a group that hears from more than one."""
    name = os.getenv("ALERT_SERVICE_NAME", "").strip() or os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    return " ".join(name.split())[:80]


# ── Delivery ────────────────────────────────────────────────────────────────

# Replaced in tests. Nothing else may choose where a message goes.
_connect: Callable[..., http.client.HTTPConnection] = http.client.HTTPSConnection


def _fit(text: str) -> str:
    """Cut to WeCom's limit on a character boundary, saying that it was cut."""
    raw = text.encode("utf-8")
    if len(raw) <= _MAX_BYTES:
        return text
    tail = "\n……（内容过长，已截断）"
    return raw[: _MAX_BYTES - len(tail.encode("utf-8"))].decode("utf-8", errors="ignore") + tail


def send(text: str) -> None:
    """Post one text message to the robot. Raises AlertError; never names the key.

    No redirect is followed and no proxy setting is read: the connection is
    to WeCom's host or it is nothing. The key travels in the query string
    because that is the only form WeCom accepts, so this uses the standard
    library's connection directly. A client that logs the address of each
    request would write the key into the service log.
    """
    key = _webhook_key()
    if key is None:
        raise AlertError("ALERT_WECOM_WEBHOOK is not set to a WeCom robot address."
                         if configured() == "misconfigured" else "ALERT_WECOM_WEBHOOK is not set.")
    body = json.dumps({"msgtype": "text", "text": {"content": _fit(text)}}, ensure_ascii=False).encode("utf-8")
    connection = _connect(_HOST, timeout=_TIMEOUT_SECONDS)
    try:
        connection.request("POST", f"{_PATH}?key={quote(key, safe='')}", body=body,
                           headers={"Content-Type": "application/json; charset=utf-8"})
        reply = connection.getresponse()
        status, raw = reply.status, reply.read(_REPLY_LIMIT)
    except (OSError, http.client.HTTPException) as exc:
        # The type and nothing more: an exception's text is not ours to vouch for.
        raise AlertError(f"WeCom could not be reached ({type(exc).__name__}).") from None
    finally:
        connection.close()
    if status != 200:
        raise AlertError(f"WeCom answered HTTP {status}.")
    try:
        code = json.loads(raw.decode("utf-8"))["errcode"]
    except (ValueError, KeyError, TypeError):
        raise AlertError("WeCom's answer could not be read.") from None
    if code != 0:
        hint = {93000: " The robot's address is not valid; it may have been removed or reset.",
                45009: " The robot is sending too often."}.get(code, "")
        raise AlertError(f"WeCom refused the message (errcode {code if isinstance(code, int) else 'unreadable'}).{hint}")


# ── What has been said ──────────────────────────────────────────────────────

@dataclass
class _Memory:
    """What the operator has been told, kept for the life of the process.

    A restart forgets it, so a problem that outlives a restart is reported
    once more. That is the right way round: the other would be a restart that
    silences a failure nobody has fixed.
    """

    standing: dict[str, float] = field(default_factory=dict)   # problem -> when it was last mentioned
    counted: dict[str, int] = field(default_factory=dict)      # failure code -> runs not yet mentioned
    mentioned: dict[str, float] = field(default_factory=dict)  # failure code -> when it was last mentioned
    delivering: bool = True
    last_sent_at: datetime | None = None
    last_failed_at: datetime | None = None


_memory = _Memory()
_lock = threading.Lock()


def reset() -> None:
    """Forget everything said. For a new process lifetime, and for tests."""
    global _memory
    with _lock:
        _memory = _Memory()


def status() -> dict[str, object]:
    """What /health shows: whether alerts can be sent, and when one last was."""
    state = configured()
    with _lock:
        if state == "ready" and not _memory.delivering:
            state = "failing"
        return {"state": state, "last_sent_at": _memory.last_sent_at, "last_failed_at": _memory.last_failed_at}


def _named(problem: str) -> str:
    if problem == LOOP_STOPPED:
        return "维护循环已停止：超时看门狗、清理和自动备份都不再运行，/health/ready 会报未就绪，需要重启服务"
    stage = problem.removeprefix("maintenance:")
    return f"维护任务 {stage} 失败" + (f"（{_STAGES[stage]}）" if stage in _STAGES else "")


def _short(revision: str) -> str:
    """`git:7b544ab` as it is; a source tree's long digest cut to what tells two apart."""
    kind, colon, digest = revision.partition(":")
    return f"{kind}{colon}{digest[:12]}" if colon else revision[:20]


def _compose(new: list[str], still: list[str], back: list[str], failures: dict[str, int], revision: str) -> str:
    service = _service()
    lines = ["【ACA 告警】" + service if service else "【ACA 告警】"]
    for title, problems in (("新出现的问题：", new), ("仍未恢复：", still)):
        if problems:
            lines.append(title)
            lines.extend(f"· {_named(problem)}" for problem in problems)
    if back:
        lines.append("已恢复：")
        lines.extend(f"· {problem.removeprefix('maintenance:')}" for problem in back)
    if failures:
        lines.append("由部署方付费的评估失败，需要运营者处理：")
        lines.extend(f"· {code} ×{count}：{_FAILURES.get(code, '见运行状态里的 error_code')}"
                     for code, count in failures.items())
        lines.append("对应的运行 ID 在服务日志里。")
    lines.append(f"版本 {_short(revision) or '未知'} ·{datetime.now(UTC):%Y-%m-%d %H:%M} UTC · 详情见 /health")
    return "\n".join(lines)


def review(problems: Iterable[str], failures: Mapping[str, int] | None = None, *, revision: str = "",
           now: float | None = None, deliver: Callable[[str], None] | None = None) -> bool:
    """Compare what is wrong now with what has been said, and say the difference.

    `problems` are the standing ones, each a stable name; `failures` counts
    runs that failed since the last call, by code. Returns whether a message
    was delivered.

    Nothing is marked as said until it has been delivered. A message WeCom
    did not take is put together again on the next call, from what is true
    then, so a problem that came and went while the robot was unreachable is
    never announced late as if it were news.
    """
    if configured() != "ready":
        return False
    moment = time.monotonic() if now is None else now
    repeat = repeat_seconds()
    current = list(dict.fromkeys(problems))
    with _lock:
        for code, count in (failures or {}).items():
            if count > 0:
                _memory.counted[code] = _memory.counted.get(code, 0) + count
        new = [problem for problem in current if problem not in _memory.standing]
        still = [problem for problem in current
                 if problem in _memory.standing and moment - _memory.standing[problem] >= repeat]
        back = [problem for problem in _memory.standing if problem not in current]
        due = {code: count for code, count in _memory.counted.items()
               if code not in _memory.mentioned or moment - _memory.mentioned[code] >= repeat}
        was_delivering = _memory.delivering
    if not (new or still or back or due):
        return False
    try:
        (deliver or send)(_compose(new, still, back, due, revision))
    except AlertError as exc:
        with _lock:
            _memory.delivering = False
            _memory.last_failed_at = datetime.now(UTC)
        # Said once when it starts, not every half minute while it lasts.
        if was_delivering:
            _LOGGER.warning("An operator alert could not be delivered: %s", exc)
        return False
    with _lock:
        for problem in new + still:
            _memory.standing[problem] = moment
        for problem in back:
            _memory.standing.pop(problem, None)
        for code, count in due.items():
            # Runs counted while this message was on its way stay counted.
            remaining = _memory.counted.get(code, 0) - count
            if remaining > 0:
                _memory.counted[code] = remaining
            else:
                _memory.counted.pop(code, None)
            _memory.mentioned[code] = moment
        _memory.delivering = True
        _memory.last_sent_at = datetime.now(UTC)
    if not was_delivering:
        _LOGGER.info("Operator alerts are being delivered again.")
    return True


# ── Command line ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m api.alerts", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test", help="Send one test message to the robot and say what happened.")
    parser.parse_args(argv)
    state = configured()
    if state == "off":
        print("Alerts are off: ALERT_WECOM_WEBHOOK is not set.", file=sys.stderr)
        return 1
    try:
        service = _service()
        send("【ACA 告警】" + (service + "\n" if service else "\n")
             + "这是一条测试消息：告警通道可用。\n"
             + f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC")
    except AlertError as exc:
        print(f"Not delivered. {exc}", file=sys.stderr)
        return 1
    print("Delivered. Check the group for the test message.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
