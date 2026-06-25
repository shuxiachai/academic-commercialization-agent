import threading
import time

import gradio as gr

from academic_agent.crew import AcademicAgent
from academic_agent.run_output import create_run_id, save_report


STAGES = [
    (75, "Agent 1 — 学术文献分析中"),
    (150, "Agent 2 — 专利图谱分析中"),
    (225, "Agent 3 — 市场情报分析中"),
    (999, "Agent 4 — 报告撰写与引用校验中"),
]
SPINNER = ["|", "/", "-", "\\"]


def run_analysis(research_topic: str):
    if not research_topic.strip():
        yield "请输入研究方向。"
        return

    run_id = create_run_id()
    result_holder = {
        "result": None,
        "path": None,
        "done": False,
        "error": None,
    }

    def _run():
        try:
            result = AcademicAgent().crew().kickoff(
                inputs={"research_topic": research_topic.strip()}
            )
            _, report_path = save_report(result.raw, run_id=run_id)
            result_holder["result"] = result.raw
            result_holder["path"] = report_path
        except Exception as exc:
            result_holder["error"] = str(exc)
        finally:
            result_holder["done"] = True

    threading.Thread(target=_run, daemon=True).start()

    start = time.time()
    tick = 0
    while not result_holder["done"]:
        elapsed = int(time.time() - start)
        stage = next(
            (label for threshold, label in STAGES if elapsed < threshold),
            STAGES[-1][1],
        )
        spin = SPINNER[tick % len(SPINNER)]
        yield (
            f"{spin} **运行中...** 已用时 {elapsed}s\n\n"
            f"> {stage}\n\n运行编号：`{run_id}`"
        )
        time.sleep(0.8)
        tick += 1

    if result_holder["error"]:
        err = result_holder["error"]
        # Show only the first meaningful line to avoid overwhelming the user
        first_line = next((l.strip() for l in err.splitlines() if l.strip()), err)
        yield (
            f"❌ **运行出错**\n\n"
            f"> {first_line}\n\n"
            f"常见原因：API 余额不足 / 网络超时 / 模型返回格式不符合要求。\n"
            f"请检查终端后台输出获取完整错误信息，然后重试。\n\n"
            f"运行编号：`{run_id}`"
        )
    else:
        report = result_holder["result"] or "报告生成失败，请重试。"
        path = result_holder["path"]
        yield f"{report}\n\n---\n\n运行编号：`{run_id}`  \n保存位置：`{path}`"


with gr.Blocks(title="Academic Commercialization Assessment Agent") as demo:
    gr.Markdown("# Academic Commercialization Assessment Agent")
    gr.Markdown(
        "输入研究方向，系统将调度 4 个专职 AI Agent 完成分析，"
        "生成带可验证引用的商业化评估报告。预计耗时 3–5 分钟。"
    )

    topic_input = gr.Textbox(
        label="Research Topic（研究方向）",
        placeholder="e.g., CRISPR gene editing applications in agriculture",
        lines=2,
    )

    with gr.Row():
        submit_btn = gr.Button("Run Analysis", variant="primary")
        clear_btn = gr.Button("Clear")

    report_output = gr.Markdown(label="Commercialization Report")

    submit_btn.click(fn=run_analysis, inputs=topic_input, outputs=report_output)
    clear_btn.click(fn=lambda: ("", ""), outputs=[topic_input, report_output])

if __name__ == "__main__":
    demo.launch()
