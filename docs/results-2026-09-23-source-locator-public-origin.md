# Production saved-source public-origin repair — 2026-09-23

## Observed failure and limits

Starting source identity: `87f2dd25d91a446f1072570d5d532d9f57d393de`.
The parent reported a clean baseline of 6,916 passed tests and 1,619 subtests
in 574.82 seconds before authorizing writes. This repair was developed on
`codex/fix-source-locator-public-origin`, not by changing frozen laboratory code.

The preceding real browser pilot issued exactly one POST and received
`403 origin_denied` before request-body/controller/key/admission work. Receipt
GET returned 404. The parent reported successful rollback: exposure enabled,
execution disabled, budgets zero and provider calls zero. These are failure and
rollback observations, not a successful native locator result or a new grant.
No private report identifiers, keys or source bytes are included here.

At `2026-09-23T05:30:46Z`, the parent's credential-free, no-follow HTTPS GET of
`/source-locator/` observed `307` with
`Location: http://academic-commercialization-agent.up.railway.app/source-locator`.
This supports an application-visible HTTP scheme behind the public HTTPS edge,
with the expected host. It does not identify the exact incoming proxy headers,
the proxy peer address, or the deployed effective trusted-proxy configuration.

The frozen `api/saved_source_receipt_app.py::_request_headers` derives expected
origin from ASGI scheme plus Host. That deterministically refuses browser HTTPS
against backend HTTP. The Dockerfile's single-worker Uvicorn command supplies
no explicit proxy-trust override; the inspected installed Uvicorn defaults to
loopback trust unless configured otherwise. This is consistent with the
[Uvicorn settings contract](https://www.uvicorn.org/settings/), not evidence of
the deployment's exact environment. No wildcard proxy trust is justified.

## Bounded repair

`Settings.public_origin`, populated by `SOURCE_LOCATOR_PUBLIC_ORIGIN`, is a
production-only configuration snapshot. Empty/unset retains ASGI-based origin
comparison. Invalid explicit configuration fails closed, disables execution
and cannot advertise an enabled page. It does not silently select legacy mode.

The new `api/saved_source_production_origin.py` validates the unmodified raw
headers. With a valid pin it independently requires Host to match the configured
authority, including its effective public port, and compares a present Origin
against the configured `(scheme, host, port)` tuple. This follows the
[origin-tuple model](https://www.rfc-editor.org/rfc/rfc6454.html), with a
deliberately restricted accepted syntax documented in the operating guide.
It never consumes Forwarded/X-Forwarded-* as authority, mutates request scope,
removes raw Origin/Host headers, or creates a spoofed Request for the old helper.

The small production header parser mirrors the frozen helper's non-origin
checks because that helper entwines origin comparison and ingress validation.
Parity tests compare both functions' actual accept/reject outcomes for GET and
POST: query prohibition, critical-header duplicates, code/key validity, media,
encoding and length rules, and bounds. The new origin grammar intentionally
rejects additional ambiguous URL spellings; this is not full parser equivalence.
Consent remains a production-only bounded prerequisite. Existing body, current
authentication, owner, durable receipt, paid admission, accounting and actual
thread-ownership code is not replaced.

The production page and whitelisted assets use the same Host/Origin pin without
requiring API credentials. `/source-locator/` explicitly returns a relative 307
target. No global redirect policy, middleware, server proxy setting or frozen
module changes. The origin pin does not establish TLS, authenticate callers,
enable execution, add spending authority, or authorize a new paid rerun.

## Local validation

All successful requests below used synthetic data and intercepted provider HTTP.
No real provider credential was read and no external provider call was made.

- Focused command: `uv run --no-sync pytest -q --maxfail=1 --tb=short
  --basetemp=<fresh-workspace-test-directory>` with
  `tests/test_saved_source_production_origin.py`,
  `tests/test_saved_source_production.py`,
  `tests/test_saved_source_production_policy.py`,
  `tests/test_saved_source_production_assets.py`,
  `tests/test_saved_source_production_default_off.py` and
  `tests/test_saved_source_receipt_app.py`: **400 passed in 28.89 seconds**.
- In an isolated pytest process, replacing only the production header function
  with the frozen ASGI-scheme function made
  `test_public_https_post_over_http_and_rollback_get_preserve_exact_delivery`
  fail as required: **403 `origin_denied` instead of 200**. The injection never
  modified disk source. After that process exited, the entire new test file
  passed: **167 passed in 3.11 seconds**.
- `uv run --no-sync --group e2e python -m e2e.source_locator_production_smoke`:
  the original direct same-origin Chromium journey passed with its existing
  consent-before-intent, exact-wire/privacy, lost-ack and GET recovery assertions.
- The same command with `--proxy`: real Chromium at `https://locator.invalid`
  passed through a fixed intercepted loopback HTTP upstream. The observer
  asserted actual ASGI scheme `http`, raw Host `locator.invalid`, and Chromium's
  unchanged HTTPS Origin. Exactly one locally intercepted selector request and
  one daily admission occurred. Exact saved text/accounting were recovered by
  one GET after execution closed, without a second selection. It also checked
  the actual relative page 307 through a manual-redirect browser fetch.

The proxy harness does not validate Railway, TLS certificates or browser
automatic redirect following. A minimal reproduction showed Playwright routing
intercepted the first synthetic 307 URL but not its following URL; that first
harness run ended in `ERR_NAME_NOT_RESOLVED` before a POST. The final harness
starts at the canonical HTTPS page and observes the slash 307 without following
it. A Chromium DNS-deny rule supplements the exact browser URL/method allowlist;
upstream fetches target only fixed loopback URLs. Python sockets retain the
existing loopback-only guard. No application assertion was loosened.

Other tooling outcomes are separate from the original origin failure: the
standard patch tool failed with Windows `helper_sandbox_lock_failed`; the
authorized native apply-patch engine applied the same patches. The first focused
pytest run hit `PermissionError [WinError 5]` in the pre-existing system pytest
temporary directory (34 passed, 314 setup errors); using a fresh workspace
temporary directory produced the 400-pass result without changing permissions.
An initial reinjection command imported application dependencies before pytest
plugin initialization and was stopped by `PytestAssertRewriteWarning`; moving
the process-local injection to `pytest_sessionstart` produced the required
defect failure without ignoring any warning.

## Handoff and remaining gates

Original production-problem failure count remains one rejected pilot. One repair
candidate has passed the focused engineering checks above; no paid retry was
attempted. The failed temp-directory run, initial proxy harness and initial
reinjection harness are retained as separate tool/test-environment outcomes,
not silently relabelled as successful validations.

Final whole-tree coverage, latest Ruff, narrow pylint, all browser journeys,
independent final review, CI and any deployment are parent-owned release gates;
the repair-author observations above do not assert those gates passed. No
commit, push or deployment was performed by this repair work. Keep execution
disabled and budgets zero during any separately authorized rollout. With a
valid current access code, synthetic question and fresh random receipt key,
an otherwise correct same-origin POST should reach `503 selector_disabled`,
while a foreign Origin should receive `403 origin_denied` before body/controller
entry. Those proposed post-deployment negative checks are not recorded here as
already observed and do not authorize new provider work.
