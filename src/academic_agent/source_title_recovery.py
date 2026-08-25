"""Precision-first recovery for structurally broken official-source titles.

Search providers occasionally return a valid regulator URL with a title that
is only encoding debris.  This module never tries to reconstruct the exact
document name: doing so would turn a display-quality repair into an unsupported
claim.  It either preserves the original bytes, derives a neutral label from a
validated URL identifier, or asks the caller to reject the source.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit


AuthorityCategory = Literal["regulatory", "clinical_registry"]
RecoveryAction = Literal["preserve", "recover", "reject", "out_of_scope"]
TitleDefectReason = Literal[
    "empty_title",
    "host_or_url_only",
    "encoding_replacement_character",
    "unicode_control_character",
    "fragmented_single_letter_tokens",
]


@dataclass(frozen=True, slots=True)
class TitleRecoveryDecision:
    """One auditable decision at the title-to-EvidenceSource seam."""

    action: RecoveryAction
    title: str | None
    reason_codes: tuple[TitleDefectReason, ...] = ()


def _is_host_or_url_only(title: str, url: str, host: str) -> bool:
    """Detect exact source identities without flagging short product names."""

    normalized_title = title.strip().lower().rstrip("/")
    normalized_url = url.strip().lower().rstrip("/")
    bare_url = re.sub(r"^https?://", "", normalized_url)
    bare_host = host.removeprefix("www.")
    return normalized_title in {
        normalized_url,
        bare_url,
        host,
        bare_host,
        f"www.{bare_host}",
    }


def structural_title_defects(
    title: str,
    url: str,
) -> tuple[TitleDefectReason, ...]:
    """Return only high-precision structural defects, never semantic guesses.

    C0/C1 controls are intentionally separate from U+FFFD.  The frozen openFDA
    sample contains literal U+0099 bytes, so checking only the usual replacement
    character would describe an upstream decoding failure as a clean title.
    """

    stripped = title.strip()
    host = (urlsplit(url).hostname or "").lower()
    reasons: list[TitleDefectReason] = []
    if not stripped:
        reasons.append("empty_title")
    elif _is_host_or_url_only(stripped, url, host):
        reasons.append("host_or_url_only")

    if "\ufffd" in title:
        reasons.append("encoding_replacement_character")
    if any(unicodedata.category(character) == "Cc" for character in title):
        reasons.append("unicode_control_character")

    # The observed FDA failure has four isolated b/I fragments followed by the
    # source host.  All three conditions are required because model numbers,
    # initials and single-letter trial arms are legitimate title content.
    alpha_tokens = re.findall(r"[A-Za-z]+", title)
    single_letter_tokens = sum(len(token) == 1 for token in alpha_tokens)
    visible_host = host.removeprefix("www.")
    if (
        single_letter_tokens >= 4
        and single_letter_tokens * 2 >= len(alpha_tokens)
        and bool(visible_host)
        and visible_host in title.lower()
    ):
        reasons.append("fragmented_single_letter_tokens")

    return tuple(reasons)


def _neutral_identifier_label(
    url: str,
    authority_category: AuthorityCategory,
) -> str | None:
    """Derive only identifiers whose syntax and host jointly establish scope."""

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if authority_category == "regulatory" and host == "accessdata.fda.gov":
        match = re.fullmatch(r"/CDRH510K/(K\d{6})\.pdf", parsed.path, re.IGNORECASE)
        if match:
            return f"FDA 510(k) record {match.group(1).upper()}"
    if authority_category == "clinical_registry" and host == "clinicaltrials.gov":
        match = re.fullmatch(r"/study/(NCT\d{8})/?", parsed.path, re.IGNORECASE)
        if match:
            return f"ClinicalTrials.gov study {match.group(1).upper()}"
    return None


def recover_official_source_title(
    title: str,
    url: str,
    *,
    authority_category: AuthorityCategory | None,
) -> TitleRecoveryDecision:
    """Preserve, safely relabel, or reject one official search-result title.

    The authority category comes from the caller's already established URL
    allowlist.  Host checks are repeated when extracting an identifier so a
    future caller cannot accidentally grant an attacker-suffix URL a regulator
    label merely by passing the wrong category.
    """

    if authority_category is None:
        return TitleRecoveryDecision(action="out_of_scope", title=None)

    reasons = structural_title_defects(title, url)
    if not reasons:
        return TitleRecoveryDecision(action="preserve", title=title)

    neutral_title = _neutral_identifier_label(url, authority_category)
    if neutral_title is None:
        return TitleRecoveryDecision(
            action="reject",
            title=None,
            reason_codes=reasons,
        )
    return TitleRecoveryDecision(
        action="recover",
        title=neutral_title,
        reason_codes=reasons,
    )
