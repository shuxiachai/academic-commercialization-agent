"""Take CrewAI's prompt-cache marks off a node's messages before they are sent.

CrewAI's executors mark the system message and the task message of every agent
call as the end of a cacheable prefix (``mark_cache_breakpoint``). Its
Anthropic provider turns each mark into ``cache_control``; the OpenAI-shaped
providers drop the mark and send nothing for it.

On Anthropic a cache write is billed at 1.25 times the input rate, and it pays
only when the same prefix is sent again. In this pipeline it is not:

- a node is one call, with no tool loop, so nothing follows the marked messages;
- the system message begins with the topic, so no two topics share a prefix;
- when a guardrail sends a node back, CrewAI replaces the task message's
  context with the failure and the previous answer, so the task message is new
  and only the system message, a small part of the prompt, could be read.

The first run through Anthropic (2026-11-12, claude-sonnet-5-5, six calls)
wrote 124,953 tokens to the cache and read none: $0.0625 of a $0.619 bill.

What goes with the marks is the one read they could have bought: a request
resent unchanged after its answer had begun and then broke would have read its
prompt back at a fraction of the price. That costs less than the writes unless
more than a quarter of all calls break that way.

CrewAI 1.14.7 has no setting for the marks; the before-call hook is the
extension point it offers. A hook that raises is swallowed by CrewAI and the
marks would stay, which costs money and breaks nothing.
"""

from __future__ import annotations

from typing import Any

from crewai.hooks import get_before_llm_call_hooks, register_before_llm_call_hook
from crewai.llms.cache import strip_cache_breakpoint


def drop_cache_marks(context: Any) -> None:
    """Before-call hook: remove the cache mark from every message, in place."""
    for message in context.messages:
        strip_cache_breakpoint(message)


def install() -> None:
    """Register the hook for every executor built after this, once per process."""
    if drop_cache_marks not in get_before_llm_call_hooks():
        register_before_llm_call_hook(drop_cache_marks)
