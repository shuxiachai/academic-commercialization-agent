"""Freeze one production-planner plan per topic (qwen3.8-27b at the time of use).

    LLM_PROVIDER=qwen QWEN_MODEL=qwen3.8-27b QWEN_API_BASE=... python build_plans.py <repo> <out.json>
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "src")]
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=False)
from academic_agent import source_pipeline as sp  # noqa: E402
from academic_agent.language import plan_topic_search  # noqa: E402

topics = json.loads((ROOT / "evals/two_word_gate_v1/topics.json").read_text(encoding="utf-8"))
plans = []
for split in ("dev", "test"):
    for topic in topics[split]:
        plan = plan_topic_search(topic, n=2)
        research_topic = " ".join(plan.search_topic.split())
        aliases = list(plan.aliases)
        plans.append({
            "split": split,
            "display_topic": topic,
            "research_topic": research_topic,
            "aliases": aliases,
            "weight_profile": sp._detect_weight_profile(research_topic),
            "anchor": sp._academic_anchor_topic(topic, research_topic, aliases),
            "planner_model": os.environ.get("QWEN_MODEL", ""),
        })
        print(f"{split} {topic!r} -> {research_topic!r} {aliases}", flush=True)
Path(sys.argv[2]).write_text(json.dumps(plans, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
