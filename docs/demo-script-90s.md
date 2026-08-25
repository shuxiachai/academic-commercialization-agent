# 90-Second Portfolio Demo Guide

## Recording goal

Show one complete decision-support journey without waiting for or paying for a
new run during recording. The video should demonstrate the product, the
evidence boundary, and one measured reliability result. It should not try to
enumerate every feature.

Use a previously completed run. Open it before recording and confirm that the
report, scorecard, source tabs, reliability panel, and downloadable artifacts
all load. Do not expose an access code, API key, owner code, private run list,
Phoenix credential, browser bookmarks, or terminal environment variables.

## Shot list and Chinese narration

### 0–10 seconds — problem and input

**Screen:** Open the live home page. Place a commercialization topic in the
composer, but do not submit it.

**Narration:**

> 科研商业化判断不能只看论文，还要同时核对专利、市场和监管证据。这个系统把研究主题或论文转换成一份可追溯、可评分的商业化评估报告。

### 10–24 seconds — constrained architecture

**Screen:** Switch to a prepared diagram or the README execution-flow section,
then briefly show the in-progress screenshot.

**Narration:**

> 我没有让大模型自由搜索。Python 检索层先验证来源、去重并冻结证据，再由三个领域节点并行分析，Writer、Reviewer 和 Scorer 只在这份证据边界内工作。

### 24–45 seconds — report and citations

**Screen:** Open the completed run. Scroll from the executive summary to one
claim with an [A], [P], or [M] citation, then open the matching source in
the Sources tab.

**Narration:**

> 报告中的每个来源编号都必须回到已注册的论文、专利或市场记录。Pydantic 和 Guardrail 会阻止虚构来源、引用断链、结构错误和评分公式漂移，而不是只依赖 Prompt 提醒模型。

### 45–62 seconds — decision surface

**Screen:** Show the scorecard, risks/opportunities, reliability panel, token
usage, and cost status. Pause long enough for labels to be readable.

**Narration:**

> 前端同时展示五维评分、证据支撑、风险机会、检查是否真正执行，以及 Token 和成本。没有运行的检查会显示未检查，不会被包装成通过。

### 62–77 seconds — production resilience

**Screen:** Show the checkpoint/recovery section in the README or the recovery
result document, then return to the live result.

**Narration:**

> 长任务按输入、证据、配置和流水线哈希保存节点级 Checkpoint。故障恢复会创建不可变子运行，只复用重新验证过的连续前缀；线上一次同版本恢复复用了四个节点，并以零次新增证据节点调用完成后续流程。

### 77–90 seconds — measured outcome and honest boundary

**Screen:** Show the measured-results table in the README, then finish on the
GitHub repository and live-demo links.

**Narration:**

> 项目目前有一千三百九十一项测试和六百二十七个子测试，并完成九十单元消融和五人盲评。盲评没有证明六阶段一定优于单模型，所以我保留失败结论。这个项目的重点不是堆 Agent，而是让 Agent 结果可验证、可恢复、可审计。

## Recording checklist

- Record at 1920×1080, 30 fps, with browser zoom at 100% or 110%.
- Use a clean browser profile or hide bookmarks, extensions, notifications,
  account avatars, and unrelated tabs.
- Preload the live home page, one completed run, the measured-results section,
  and the checkpoint result before recording.
- Use a completed run rather than clicking **Run Analysis**. This keeps the take
  deterministic, avoids a three-minute pause, and incurs no new provider cost.
- Keep one citation-to-source interaction in the final cut; it is the clearest
  evidence that this is more than a report-generation UI.
- Keep one explicit non-success state (not_run, not_observed, or
  not_inspectable) visible if the chosen run has one.
- Add Chinese captions and short English overlays for: Validated evidence,
  Guardrails, Checkpoint recovery, and Measured evaluation.
- Do not claim autonomous Tool Calling, classic vector RAG, six-stage
  superiority, production SLOs, exactly-once execution, adoption, or ROI.
- End with both links on screen for at least two seconds:
  [live application](https://academic-commercialization-agent.up.railway.app)
  and [GitHub repository](https://github.com/shuxiachai/academic-commercialization-agent).

## Before publishing

Watch the exported video once without sound and once audio-only. The silent pass
checks whether the product story is visually understandable; the audio-only
pass catches narration that depends on unreadable UI text. Verify every number
against [the case study](portfolio-case-study.md) immediately before upload.
