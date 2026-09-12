"""Read the legacy cap's arithmetic receipt without claiming market comparability.

Only the production guardrail captures the original validated model score.
Saved/reused output carries that receipt; readers check its shape and arithmetic,
not its authenticity. Trust comes from post-guardrail publication and checkpoint
identity, never from a model writing this version string. Historical capped
scores alone cannot reconstruct an original score.
"""

import math
import re
from typing import Any


VERSION = "legacy-market-cap-audit-v1"
_FLAG = re.compile(
    r"high \([0-9]+× spread: [0-9]+(?:\.[0-9]+)?(?:e[+-][0-9]+)?–"
    r"[0-9]+(?:\.[0-9]+)?(?:e[+-][0-9]+)? bn USD\)"
)


def legacy_signal(payload: dict[str, Any]) -> str:
    if "market_uncertainty" in payload and payload["market_uncertainty"] is None:
        return "not_triggered"
    flag = payload.get("market_uncertainty")
    return "triggered" if isinstance(flag, str) and _FLAG.fullmatch(flag) else "unavailable"


def capture_cap(pre_cap_score: float, payload: dict[str, Any]) -> dict[str, Any]:
    """Record observed pre/post values, not a second implementation of scoring."""
    post = payload["market_accessibility"]
    # The frozen producer sets this field only inside the trigger branch.
    # Presentation grammar may later reject an unusual formatted ratio, but
    # that must not rewrite the observed branch into "not triggered".
    triggered = payload["market_uncertainty"] is not None
    return {
        "version": VERSION,
        "pre_cap_score": pre_cap_score,
        "post_cap_score": post,
        "cap": 3.5,
        "triggered": triggered,
        "applied": post < pre_cap_score,
        "deduction": round(pre_cap_score - post, 1),
        "reason": "legacy_untyped_spread_gt_5" if triggered else "legacy_cap_not_triggered",
    }


def readable_cap(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Reject partial, forged-shape or stale receipts without repairing scores."""
    audit = payload.get("market_cap_audit")
    if not isinstance(audit, dict) or audit.get("version") != VERSION:
        return None
    pre, post = audit.get("pre_cap_score"), audit.get("post_cap_score")
    if not all(type(x) in (int, float) and math.isfinite(x) and 1 <= x <= 5 for x in (pre, post)):
        return None
    if type(audit.get("triggered")) is not bool or type(audit.get("applied")) is not bool:
        return None
    delta = audit.get("deduction")
    if type(delta) not in (int, float) or not math.isfinite(delta):
        return None
    signal = legacy_signal(payload)
    if signal == "unavailable" or audit["triggered"] != (signal == "triggered"):
        return None
    expected = min(pre, 3.5) if audit["triggered"] else pre
    if (type(payload.get("market_accessibility")) not in (int, float)
            or audit.get("cap") != 3.5 or post != payload.get("market_accessibility")
            or post != expected or delta != round(pre - post, 1)
            or audit["applied"] != (post < pre)
            or audit.get("reason") != ("legacy_untyped_spread_gt_5" if audit["triggered"] else "legacy_cap_not_triggered")):
        return None
    return audit
