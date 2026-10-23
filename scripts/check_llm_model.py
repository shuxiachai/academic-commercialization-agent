"""Check that a model works with this pipeline before the deployment switches to it.

    uv run python scripts/check_llm_model.py [--long]
    railway run python scripts/check_llm_model.py --long   # with the deployment's own variables

Reads the variables the server reads (LLM_PROVIDER, the provider's key, its
model variable such as QWEN_MODEL, any *_API_BASE), then sends one tiny
request down each production call path:
- the language helper, which plans the search and translates;
- an agent's LLM in JSON mode, as the evidence, scoring and review agents use it;
- an agent's LLM in free-text mode, as the report writer uses it.

The check prints what the model needed adapting (llm_parameter_fallback),
for example thinking mode for a model that cannot turn it off.

``--long`` also times one long answer, a few thousand tokens. It estimates
whether the report writer's call fits the per-call budget the worker gives
each agent.

Exits 1 when a path fails. The few requests are billed like any other.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

# The report writer's longest answers run to about 6,500 tokens (held-out v2).
_WRITER_TOKENS = 6_500
_LONG_PROMPT = ("Write a structured 1,500-word technical brief on perovskite solar cells for building-integrated "
                "photovoltaics: maturity, stability, manufacturing, market and risks. Use Markdown headings.")


def _line(label: str, ok: bool, seconds: float, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label:46} {seconds:5.1f}s  {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--long", action="store_true", help="also time one long answer against the per-call budget")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")  # never overrides variables already set
    from academic_agent import language
    from academic_agent import llm_parameter_fallback as fallback
    from academic_agent.llm_config import create_llm, resolve_provider_config
    from academic_agent.runtime_budget import REQUEST_TIMEOUT_SECONDS
    from api.runs import _public_failure_reason

    config = resolve_provider_config()
    print(f"provider {config.provider} | model {config.model} | endpoint {config.base_url}")
    failures = 0

    start = time.monotonic()
    reply = language._llm_call("Reply with the single word: ready", system="Answer tersely.", max_tokens=20)
    ok = bool(reply)
    failures += not ok
    _line("language helper (search planning, translation)", ok, time.monotonic() - start,
          repr(reply[:40]) if ok else "no answer; in a run this falls back to the raw topic silently")

    for json_mode, label in ((True, "agent LLM, JSON mode"), (False, "agent LLM, free text (report writer)")):
        start = time.monotonic()
        try:
            llm = create_llm(json_mode=json_mode, temperature=0.0 if json_mode else None)
            prompt = 'Reply with the JSON object {"ok": true}.' if json_mode else "Reply with the word ok."
            out = str(llm.call([{"role": "user", "content": prompt}]))
            ok = json.loads(out).get("ok") is True if json_mode else bool(out.strip())
            detail = repr(out[:40])
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            ok, detail = False, f"{_public_failure_reason(f'{type(exc).__name__}: {exc}')} ({str(exc)[:200]})"
        failures += not ok
        _line(label, ok, time.monotonic() - start, detail)

    if args.long and not failures:
        start = time.monotonic()
        out = str(create_llm().call([{"role": "user", "content": _LONG_PROMPT}]))
        seconds = time.monotonic() - start
        tokens = max(1, len(out) // 4)  # content only; thinking tokens are on top
        estimate = _WRITER_TOKENS / (tokens / seconds)
        ok = estimate < REQUEST_TIMEOUT_SECONDS
        failures += not ok
        _line("long answer, writer-sized estimate", ok, seconds,
              f"~{tokens / seconds:.0f} content tokens/s; a {_WRITER_TOKENS}-token report ~{estimate:.0f}s "
              f"of the {REQUEST_TIMEOUT_SECONDS}s per-call budget")

    learned = fallback.learned(config.base_url, config.model)
    if learned:
        changes = ", ".join(f"{name}={'omitted' if value is fallback.OMIT else value!r}" for name, value in learned.items())
        print(f"adapted for this model: {changes}")
    print("OK: the pipeline can use this model." if not failures else f"{failures} path(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
