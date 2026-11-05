"""Ask the providers whether they accept an account's keys, when it saves them.

An account pays for its runs with keys it types in once. Until this module a
mistyped key, a key for another provider or a misspelt model name was only
discovered minutes later, when the run it had started failed. The check
happens at the moment the keys are saved instead.

What it asks and what it costs: one unbilled read per service. The model
provider's model list, and the search service's account or usage record. No
completion is requested and no search is run, so the account's keys are never
charged for being checked.

Where the requests go: only to the provider's own endpoint, the same one a run
with those keys would use (``resolve_provider_config``), and to the two fixed
search hosts. Nothing in the request chooses a destination, so this cannot be
turned into a request to an arbitrary address.

Three answers, never two. A provider that says the key is not valid is
``rejected``. Anything that is not an answer about the key (a timeout, a
server error, a key that is real but not allowed to list models) is
``unverified``: the caller keeps the keys and is told they were not checked.
A check that cannot run must never stand between someone and a key that works.

The keys are neither stored nor logged here, and provider error text is never
passed on: it can quote part of the key back.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass

import httpx

from academic_agent.llm_config import resolve_provider_config

# DashScope answers a model-list request in three to four seconds from some
# networks. Two probes run side by side, so this bounds the whole check.
TIMEOUT_SECONDS = 8.0
# A model list is tens of kilobytes. The cap only keeps a misbehaving endpoint
# from being read without limit; over it the model is reported as unknown.
_MAX_BODY_BYTES = 2_000_000
_ANTHROPIC_VERSION = "2023-06-01"

ACCEPTED, REJECTED, UNVERIFIED = "accepted", "rejected", "unverified"
LISTED, NOT_LISTED, UNKNOWN = "listed", "not_listed", "unknown"

# Every key these services issue is printable ASCII without spaces. A pasted
# key with a space or a line break inside it cannot be one, and it could not
# be put in a request header either, so it is refused without a request.
_KEY_SHAPE = re.compile(r"[\x21-\x7e]{1,400}")

_SEARCH_ENDPOINTS = {
    "tavily": "https://api.tavily.com/usage",
    "serper": "https://google.serper.dev/account",
}


@dataclass(frozen=True)
class KeyCheck:
    """What each provider said. Holds no key and no provider text."""

    llm: str
    model: str
    search: str


def enabled() -> bool:
    """Whether this deployment checks keys at all.

    On unless ``KEY_CHECK`` says otherwise. An operator whose host cannot
    reach the providers, or who does not want the server making these
    requests, turns it off; every answer is then ``unverified`` and the page
    does not call the check.
    """
    return os.getenv("KEY_CHECK", "on").strip().lower() not in {"off", "0", "false", "no"}


def _key_verdict(status: int, body: bytes) -> str:
    """Read a provider's status as an answer about the key, or as no answer."""
    if status == 200:
        return ACCEPTED
    if status in (401, 403):
        # A real key can be refused this one read: OpenAI keys are issued
        # with scopes, Anthropic answers 403 `permission_error`. That says
        # nothing about whether a run would work.
        text = body[:4000].decode("utf-8", "replace").lower()
        if "scope" in text or "permission" in text:
            return UNVERIFIED
        return REJECTED
    return UNVERIFIED


def _model_verdict(body: bytes, model: str) -> str:
    """Whether the provider's own list names the model.

    ``not_listed`` is only said when the whole list was read. A list that is
    cut short, paged or unreadable leaves the model ``unknown``.
    """
    try:
        payload = json.loads(body)
    except ValueError:
        return UNKNOWN
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return UNKNOWN
    names = {row.get("id") for row in rows if isinstance(row, dict)}
    if model in names:
        return LISTED
    return UNKNOWN if payload.get("has_more") else NOT_LISTED


async def _read(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> tuple[int, bytes, bool]:
    """GET `url`; return status, body up to the cap, and whether it was whole."""
    async with client.stream("GET", url, headers=headers) as response:
        chunks, size = [], 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > _MAX_BODY_BYTES:
                return response.status_code, b"".join(chunks), False
            chunks.append(chunk)
        return response.status_code, b"".join(chunks), True


async def _check_llm(client: httpx.AsyncClient, provider: str, api_key: str, model: str) -> tuple[str, str]:
    if not _KEY_SHAPE.fullmatch(api_key):
        return REJECTED, UNKNOWN
    try:
        config = resolve_provider_config(provider=provider, api_key=api_key, model=model)
    except RuntimeError:
        return UNVERIFIED, UNKNOWN
    if config.provider == "anthropic":
        url = f"{config.base_url}/v1/models?limit=1000"
        headers = {"x-api-key": config.api_key, "anthropic-version": _ANTHROPIC_VERSION}
    else:
        url = f"{config.base_url}/models"
        headers = {"Authorization": f"Bearer {config.api_key}"}
    try:
        status, body, whole = await _read(client, url, headers)
    except (httpx.HTTPError, OSError):
        return UNVERIFIED, UNKNOWN
    verdict = _key_verdict(status, body)
    if verdict != ACCEPTED or not whole:
        return verdict, UNKNOWN
    return verdict, _model_verdict(body, config.model)


async def _check_search(client: httpx.AsyncClient, service: str, api_key: str) -> str:
    if not _KEY_SHAPE.fullmatch(api_key):
        return REJECTED
    url = _SEARCH_ENDPOINTS[service]
    headers = {"X-API-KEY": api_key} if service == "serper" else {"Authorization": f"Bearer {api_key}"}
    try:
        status, body, _ = await _read(client, url, headers)
    except (httpx.HTTPError, OSError):
        return UNVERIFIED
    return _key_verdict(status, body)


async def check(
    *, provider: str, llm_api_key: str, model: str, search: str, search_api_key: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> KeyCheck:
    """Check one complete key set. Never raises for anything a provider does.

    Redirects are not followed: a key must not travel to wherever a response
    points. ``transport`` exists for tests, which answer the requests locally.
    """
    if not enabled():
        return KeyCheck(UNVERIFIED, UNKNOWN, UNVERIFIED)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False, transport=transport) as client:
            (llm, listed), found = await asyncio.wait_for(
                asyncio.gather(
                    _check_llm(client, provider, llm_api_key, model),
                    _check_search(client, search, search_api_key),
                ),
                timeout=TIMEOUT_SECONDS + 2.0,
            )
    except (TimeoutError, httpx.HTTPError, OSError):
        return KeyCheck(UNVERIFIED, UNKNOWN, UNVERIFIED)
    return KeyCheck(llm, listed, found)
