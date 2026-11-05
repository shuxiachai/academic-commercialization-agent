"""Does CrewAI's pre-call context check replace the evidence registry?

Run in an environment with the CrewAI version under test:

    uv run python -X utf8 docs/artifacts/2026-11-05-crewai-1.15.29-comparison/compaction_probe.py

It builds the model object through this project's own factory, replaces both
of its call methods and blocks name resolution, so no request leaves the
machine. On CrewAI 1.14.7 the check does not exist and the script says so.
"""
import logging
import os
import socket

os.environ["AGENT_OBSERVABILITY_ENABLED"] = "false"
os.environ["OTEL_SDK_DISABLED"] = "true"
logging.disable(logging.CRITICAL)

import crewai  # noqa: E402
from crewai.utilities import agent_utils  # noqa: E402

from academic_agent import llm_config  # noqa: E402

MARK = "SOURCE-REGISTRY-ROW"
REGISTRY = " ".join(f"{MARK}-{i} title of a validated source with its identifier and year." for i in range(700))


def _no_network(*args, **kwargs):
    raise RuntimeError("network call attempted")


def probe(model: str) -> None:
    calls = []
    llm = llm_config.create_llm(provider="qwen", api_key="sk-probe", model=model)

    async def fake_acall(messages, *args, **kwargs):
        calls.append(messages)
        return "<summary>compacted by the model</summary>"

    object.__setattr__(llm, "call", lambda messages, *a, **k: "<summary>compacted by the model</summary>")
    object.__setattr__(llm, "acall", fake_acall)
    for label, tail in (
        ("first turn", []),
        ("second turn", [
            {"role": "assistant", "content": "Thought: I will answer."},
            {"role": "user", "content": "Invalid format. Return the final answer."},
        ]),
    ):
        messages = [
            {"role": "system", "content": "You are the analyst."},
            {"role": "user", "content": "Validated source registry: " + REGISTRY},
            *tail,
        ]
        before = len(calls)
        agent_utils._proactively_summarize_context(
            llm=llm, messages=messages, callbacks=[], printer=None, tools=None, response_model=None, verbose=False,
        )
        rows = sum(str(message["content"]).count(MARK) for message in messages)
        print(f"{model}: assumed usable window {llm.get_context_window_size():,}; {label}: "
              f"registry rows left {rows} of 700; summarising calls {len(calls) - before}")


if __name__ == "__main__":
    print("crewai", crewai.__version__, "| registry of about", (len(REGISTRY) + 3) // 4, "tokens at four characters each")
    if not hasattr(agent_utils, "_proactively_summarize_context"):
        print("this version has no pre-call context check")
    else:
        socket.getaddrinfo = _no_network
        for name in ("qwen3.6-plus", "qwen3.7-max-2026-06-08"):
            probe(name)
