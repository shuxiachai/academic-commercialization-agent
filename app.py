import json
import sys
import threading
import time
import traceback


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

import gradio as gr

from academic_agent.crew import AcademicAgent
from academic_agent.run_output import (
    create_run_id,
    save_error,
    save_report,
    save_scores,
    save_source_collection,
)
from academic_agent.source_pipeline import collect_source_collection


# Labels shown while each task is RUNNING.
# When task N completes, the callback advances the label to index N
# (i.e., shows the label for the task that is now starting).
TASK_STAGE_LABELS = [
    "Agent 1 — 学术文献分析中",
    "Agent 2 — 专利图谱分析中",
    "Agent 3 — 市场情报分析中",
    "Agent 4 — 报告撰写中",
    "Agent 5 — 质量审查与引用校验中",
    "Agent 6 — 商业化评分中",
]
SPINNER = ["|", "/", "-", "\\"]


def _render_score_card(scores_json: str, topic: str) -> str:
    """Render CommercializationScore JSON as a Markdown summary card."""
    try:
        s = json.loads(scores_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    trl = s.get("trl_score", "?")
    pat = s.get("patent_strength", "?")
    mkt = s.get("market_accessibility", "?")
    evi = s.get("evidence_confidence", "?")
    overall = s.get("overall_score", "?")
    risks = "\n".join(f"- {r}" for r in s.get("key_risks", []))
    opps = "\n".join(f"- {o}" for o in s.get("key_opportunities", []))

    return f"""## Commercialization Readiness Scorecard

**Topic:** {topic}  |  **Overall Score: {overall} / 100**

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| Technology Readiness (TRL) | {trl} / 9 | {s.get("trl_rationale", "")} |
| IP Landscape Navigability | {pat} / 5 | {s.get("patent_rationale", "")} |
| Market Accessibility | {mkt} / 5 | {s.get("market_rationale", "")} |
| Evidence Confidence | {evi} / 5 | {s.get("evidence_rationale", "")} |

**Scoring rationale:** {s.get("scoring_rationale", "")}

**Key Risks:**
{risks}

**Key Opportunities:**
{opps}

---

"""


def run_analysis(research_topic: str):
    if not research_topic.strip():
        yield "请输入研究方向。", None
        return

    run_id = create_run_id()
    result_holder = {
        "result": None,       # Markdown report (Task 5 output)
        "path": None,
        "scores": None,       # JSON scorecard (Task 6 output)
        "scores_path": None,
        "done": False,
        "error": None,
        "error_path": None,
        "current_stage": "来源检索与验证中",
    }

    # Counts completed tasks; callback advances the stage label.
    completed_tasks = [0]

    def on_task_complete(_task_output) -> None:
        completed_tasks[0] += 1
        idx = completed_tasks[0]
        if idx < len(TASK_STAGE_LABELS):
            result_holder["current_stage"] = TASK_STAGE_LABELS[idx]

    def _run():
        try:
            result_holder["current_stage"] = "来源检索与验证中"
            source_collection = collect_source_collection(research_topic.strip())
            save_source_collection(
                source_collection.model_dump_json(indent=2),
                run_id=run_id,
            )
            result_holder["current_stage"] = TASK_STAGE_LABELS[0]

            result = AcademicAgent(
                source_collection,
                task_callback=on_task_complete,
            ).crew().kickoff(inputs=source_collection.crew_inputs())

            # With 6 tasks:
            #   tasks_output[-2] = Task 5 (reviewer)  → the Markdown report
            #   tasks_output[-1] = Task 6 (scorer)    → the JSON scorecard
            tasks_output = getattr(result, "tasks_output", None) or []
            if len(tasks_output) >= 2:
                report_raw = tasks_output[-2].raw
                scores_raw = tasks_output[-1].raw
            else:
                # Fallback: fewer tasks than expected (e.g., scorer failed)
                report_raw = result.raw
                scores_raw = None

            _, report_path = save_report(report_raw, run_id=run_id)
            result_holder["result"] = report_raw
            result_holder["path"] = report_path

            if scores_raw:
                scores_path = save_scores(scores_raw, run_id=run_id)
                result_holder["scores"] = scores_raw
                result_holder["scores_path"] = scores_path

        except Exception as exc:
            error_details = traceback.format_exc()
            error_path = save_error(error_details, run_id=run_id)
            print(error_details, file=sys.stderr, flush=True)
            result_holder["error"] = str(exc)
            result_holder["error_path"] = error_path
        finally:
            result_holder["done"] = True

    threading.Thread(target=_run, daemon=True).start()

    start = time.time()
    tick = 0
    while not result_holder["done"]:
        elapsed = int(time.time() - start)
        stage = result_holder["current_stage"]
        spin = SPINNER[tick % len(SPINNER)]
        yield (
            f"{spin} **运行中...** 已用时 {elapsed}s\n\n"
            f"> {stage}\n\n运行编号：`{run_id}`"
        ), None
        time.sleep(0.8)
        tick += 1

    if result_holder["error"]:
        err = result_holder["error"]
        error_path = result_holder["error_path"]
        first_line = next((l.strip() for l in err.splitlines() if l.strip()), err)
        yield (
            f"❌ **运行出错**\n\n"
            f"> {first_line}\n\n"
            f"常见原因：API 余额不足 / 网络超时 / 模型返回格式不符合要求。\n"
            f"完整错误日志：`{error_path}`\n\n"
            f"运行编号：`{run_id}`"
        ), None
    else:
        report = result_holder["result"] or "报告生成失败，请重试。"
        path = result_holder["path"]
        scores_json = result_holder["scores"]
        score_card = (
            _render_score_card(scores_json, research_topic.strip())
            if scores_json
            else ""
        )
        full_output = (
            f"{score_card}{report}\n\n---\n\n"
            f"运行编号：`{run_id}`  \n保存位置：`{path}`"
        )
        yield full_output, str(path) if path else None


with gr.Blocks(title="Academic Commercialization Assessment Agent") as demo:
    gr.Markdown("# Academic Commercialization Assessment Agent")
    gr.Markdown(
        "输入研究方向，系统将调度 6 个专职 AI Agent 完成分析，"
        "生成带可验证引用的商业化评估报告及量化评分卡。预计耗时 5–8 分钟。"
    )

    topic_input = gr.Textbox(
        label="Research Topic（研究方向）",
        placeholder="e.g., perovskite solar cells for building-integrated photovoltaics",
        lines=2,
    )

    with gr.Row():
        submit_btn = gr.Button("Run Analysis", variant="primary")
        clear_btn = gr.Button("Clear")

    report_output = gr.Markdown(label="Commercialization Report")
    download_output = gr.File(label="下载报告 (.md)")

    submit_btn.click(
        fn=run_analysis,
        inputs=topic_input,
        outputs=[report_output, download_output],
    )
    clear_btn.click(
        fn=lambda: ("", "", None),
        outputs=[topic_input, report_output, download_output],
    )

if __name__ == "__main__":
    demo.launch()
