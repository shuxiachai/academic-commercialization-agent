# ============================================================
# ORIGINAL DEMO: LatestAiDevelopmentCrew with 2 agents
#   原始 Demo：仅含 researcher + reporting_analyst 两个 Agent
#
# MODIFIED: Academic commercialization assessment with:
#   改造为学术成果商业化评估系统，包含：
#   - 6 specialized agents and tasks (ADDED: report_reviewer, commercialization_scorer)
#     6 个专职 Agent 和对应 Task（新增：质量审查员、量化评分员）
#   - Structured EvidenceReport outputs for research tasks
#     前三个研究类 Task 输出结构化 JSON 证据报告
#   - Source-specific guardrails with automatic retries
#     每个研究 Task 配有来源校验 guardrail，失败自动重试
#   - Citation-integrity guardrail on the final report
#     最终报告配有引用完整性 guardrail
#   - CommercializationScore JSON output from scoring task
#     评分 Task 输出结构化 JSON 评分卡
#   - task_callback for real-time frontend progress tracking
#     task_callback 支持前端实时进度追踪（替代时间估算）
#   - Explicit context wiring and API rate limiting
#     显式上下文传递 + API 限速（max_rpm=6）
# ============================================================

from collections.abc import Callable
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from academic_agent.evidence import (
    make_evidence_guardrail,
    make_final_report_guardrail,
    make_reviewer_guardrail,
    make_scoring_guardrail,
)
from academic_agent.llm_config import create_deepseek_llm
from academic_agent.source_pipeline import SourceCollection


@CrewBase
class AcademicAgent:
    """Academic Commercialization Assessment Crew.
    学术成果商业化评估 Crew，包含 6 个顺序执行的专职 Agent。
    """

    def __init__(
        self,
        source_collection: SourceCollection,
        task_callback: Callable[[Any], None] | None = None,
    ) -> None:
        # 接收由 source_pipeline 预收集并验证的来源数据集
        # Receives pre-validated source collection from source_pipeline
        self.source_collection = source_collection
        # 可选回调：每个 Task 完成时触发，用于前端实时进度追踪
        # Optional callback: fires on each Task completion for frontend progress
        self.task_callback = task_callback

    agents: list[BaseAgent]
    tasks: list[Task]

    # ----------------------------------------------------------
    # AGENTS
    # 六个专职 Agent，角色和目标定义在 config/agents.yaml 中
    # Six specialized agents; roles/goals defined in agents.yaml
    # ----------------------------------------------------------

    @agent
    def academic_researcher(self) -> Agent:
        """Agent 1 — 学术文献分析师 / Academic Literature Analyst
        使用 JSON 模式输出，确保结构化 JSON 证据报告格式正确。
        JSON mode enabled to ensure structured evidence output.
        """
        return Agent(
            config=self.agents_config["academic_researcher"],  # type: ignore[index]
            llm=create_deepseek_llm(json_mode=True, temperature=0.0),
            verbose=True,
            inject_date=True,
        )

    @agent
    def patent_analyst(self) -> Agent:
        """Agent 2 — 专利图谱分析师 / Patent Landscape Analyst
        仅接受来自官方专利库（Google Patents / WIPO / Espacenet）的来源。
        Only accepts sources from official patent registries.
        """
        return Agent(
            config=self.agents_config["patent_analyst"],  # type: ignore[index]
            llm=create_deepseek_llm(json_mode=True, temperature=0.0),
            verbose=True,
            inject_date=True,
        )

    @agent
    def market_intelligence_analyst(self) -> Agent:
        """Agent 3 — 市场情报分析师 / Market & Competitive Intelligence Analyst
        来源经过域名白名单过滤，屏蔽社交媒体和低可信度平台。
        Sources filtered through domain allowlist; social media blocked.
        """
        return Agent(
            config=self.agents_config[
                "market_intelligence_analyst"
            ],  # type: ignore[index]
            llm=create_deepseek_llm(json_mode=True, temperature=0.0),
            verbose=True,
            inject_date=True,
        )

    @agent
    def commercialization_report_writer(self) -> Agent:
        """Agent 4 — 报告撰写师 / Commercialization Report Writer
        不使用 JSON 模式，输出自由格式 Markdown 报告。
        Free-form mode (no JSON); outputs full Markdown report.
        """
        return Agent(
            config=self.agents_config[
                "commercialization_report_writer"
            ],  # type: ignore[index]
            llm=create_deepseek_llm(),  # 自由文本模式 / Free-text mode
            verbose=True,
        )

    @agent
    def report_reviewer(self) -> Agent:
        """Agent 5 — 质量审查员 / Report Quality Reviewer  [ADDED]
        对 Agent 4 的草稿进行 final inspection，检查四类问题：
        Performs final inspection on Agent 4's draft, checking four issues:
          1. 引用完整性 / Citation integrity (body ↔ References)
          2. 悬空数字 / Unsupported numerical claims
          3. 过度乐观语言 / Overconfident language
          4. 专利法律免责 / Patent legal disclaimer framing
        """
        return Agent(
            config=self.agents_config["report_reviewer"],  # type: ignore[index]
            llm=create_deepseek_llm(),  # 自由文本模式 / Free-text mode
            verbose=True,
        )

    @agent
    def commercialization_scorer(self) -> Agent:
        """Agent 6 — 商业化评分员 / Commercialization Readiness Scorer  [ADDED]
        基于 Task 1/2/3 的结构化证据 JSON 输出量化评分卡。
        Scores four dimensions from Tasks 1-3 evidence JSON; outputs JSON scorecard.
        使用 JSON 模式确保评分输出格式正确。
        JSON mode enabled to ensure structured scorecard output.
        """
        return Agent(
            config=self.agents_config["commercialization_scorer"],  # type: ignore[index]
            llm=create_deepseek_llm(json_mode=True, temperature=0.0),
            verbose=True,
        )

    # ----------------------------------------------------------
    # TASKS
    # 六个顺序执行的任务，详细描述在 config/tasks.yaml 中
    # Six sequential tasks; descriptions defined in tasks.yaml
    # ----------------------------------------------------------

    @task
    def academic_research_task(self) -> Task:
        """Task 1 — 学术文献分析 / Academic Literature Analysis
        Guardrail 验证 Agent 输出的 JSON 是否引用了合法的 A 前缀来源。
        Guardrail checks that JSON output only references valid A-prefix source IDs.
        """
        return Task(
            config=self.tasks_config["academic_research_task"],  # type: ignore[index]
            guardrail=make_evidence_guardrail(
                "A",                                              # 来源 ID 前缀 / Source ID prefix
                self.source_collection.topic,
                self.source_collection.sources_for_prefix("A"),  # 预验证的学术来源 / Pre-validated academic sources
                self.source_collection.queries_for_prefix("A"),
            ),
            guardrail_max_retries=2,  # 校验失败最多重试 2 次 / Max 2 retries on guardrail failure
        )

    @task
    def patent_analysis_task(self) -> Task:
        """Task 2 — 专利图谱分析 / Patent Landscape Analysis
        Guardrail 验证 Agent 输出只引用 P 前缀的官方专利来源。
        Guardrail checks that output only references valid P-prefix patent sources.
        """
        return Task(
            config=self.tasks_config["patent_analysis_task"],  # type: ignore[index]
            guardrail=make_evidence_guardrail(
                "P",
                self.source_collection.topic,
                self.source_collection.sources_for_prefix("P"),  # 预验证的专利来源 / Pre-validated patent sources
                self.source_collection.queries_for_prefix("P"),
            ),
            guardrail_max_retries=2,
        )

    @task
    def market_intelligence_task(self) -> Task:
        """Task 3 — 市场情报分析 / Market Intelligence Analysis
        Guardrail 验证 Agent 输出只引用 M 前缀的市场来源。
        Guardrail checks that output only references valid M-prefix market sources.
        """
        return Task(
            config=self.tasks_config[
                "market_intelligence_task"
            ],  # type: ignore[index]
            guardrail=make_evidence_guardrail(
                "M",
                self.source_collection.topic,
                self.source_collection.sources_for_prefix("M"),  # 预验证的市场来源 / Pre-validated market sources
                self.source_collection.queries_for_prefix("M"),
            ),
            guardrail_max_retries=2,
        )

    @task
    def commercialization_report_task(self) -> Task:
        """Task 4 — 综合报告撰写 / Commercialization Report Writing
        以前三个 Task 的输出作为上下文，撰写完整 Markdown 报告。
        Uses outputs of Tasks 1-3 as context to write the full Markdown report.
        Guardrail 检查报告结构完整性和引用一致性。
        Guardrail checks report structure completeness and citation consistency.
        """
        context_tasks = [
            self.academic_research_task(),     # Task 1 输出作为上下文 / Task 1 output as context
            self.patent_analysis_task(),       # Task 2 输出作为上下文 / Task 2 output as context
            self.market_intelligence_task(),   # Task 3 输出作为上下文 / Task 3 output as context
        ]
        localized = (
            tuple(self.source_collection.localized_headings)
            if self.source_collection.localized_headings
            else None
        )
        return Task(
            config=self.tasks_config[
                "commercialization_report_task"
            ],  # type: ignore[index]
            context=context_tasks,
            guardrail=make_final_report_guardrail(
                context_tasks,
                required_headings=localized,
                output_language=self.source_collection.output_language,
            ),
            guardrail_max_retries=1,
            markdown=True,
        )

    @task
    def report_review_task(self) -> Task:
        """Task 5 — 报告质量审查 / Report Quality Review  [ADDED]
        以 Task 4 的草稿报告 + Tasks 1/2/3 原始证据 JSON 作为上下文。
        Takes Task 4 draft + Tasks 1/2/3 raw evidence JSON as context.
        Reviewer 可以将报告结论与原始证据交叉核验，捕获事实性偏差。
        Reviewer can cross-check report conclusions against raw evidence.
        输出为修正后的最终报告，末尾附 Reviewer Notes 列出所有修改。
        Outputs corrected final report with Reviewer Notes section appended.
        Guardrail 防止审查员意外截断报告或删除引用标注。
        Guardrail prevents accidental truncation or citation removal.
        """
        report_task = self.commercialization_report_task()
        return Task(
            config=self.tasks_config["report_review_task"],  # type: ignore[index]
            context=[
                report_task,                        # Task 4 报告草稿 / Report draft
                self.academic_research_task(),      # Task 1 原始学术证据 / Raw academic evidence
                self.patent_analysis_task(),        # Task 2 原始专利证据 / Raw patent evidence
                self.market_intelligence_task(),    # Task 3 原始市场证据 / Raw market evidence
            ],
            guardrail=make_reviewer_guardrail(
                report_task,
                localized_headings=(
                    tuple(self.source_collection.localized_headings)
                    if self.source_collection.localized_headings
                    else None
                ),
                output_language=self.source_collection.output_language,
            ),
            guardrail_max_retries=1,
            markdown=True,
        )

    @task
    def commercialization_scoring_task(self) -> Task:
        """Task 6 — 量化评分 / Commercialization Readiness Scoring  [ADDED]
        以 Task 1/2/3 的结构化证据 JSON 为输入，输出量化评分卡。
        Uses Tasks 1-3 evidence JSON as input; outputs a structured scorecard.
        独立于报告撰写流程，直接评分原始证据，确保客观性。
        Independent of the report pipeline; scores raw evidence for objectivity.
        Guardrail 验证 JSON 格式符合 CommercializationScore 模型。
        Guardrail validates JSON against CommercializationScore schema.
        """
        return Task(
            config=self.tasks_config["commercialization_scoring_task"],  # type: ignore[index]
            context=[                              # 直接读取原始证据 JSON / Reads raw evidence JSON
                self.academic_research_task(),    # Task 1 学术证据
                self.patent_analysis_task(),      # Task 2 专利证据
                self.market_intelligence_task(),  # Task 3 市场证据
            ],
            guardrail=make_scoring_guardrail(),   # JSON 格式校验 / JSON schema validation
            guardrail_max_retries=2,
        )

    # ----------------------------------------------------------
    # CREW
    # 将所有 Agent 和 Task 组装成顺序执行的 Crew
    # Assembles all agents and tasks into a sequential Crew
    # ----------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        """Create the academic commercialization assessment crew.
        创建学术成果商业化评估 Crew，顺序执行 6 个 Task。
        """
        return Crew(
            agents=self.agents,           # 自动收集所有 @agent 方法 / Auto-collects all @agent methods
            tasks=self.tasks,             # 自动收集所有 @task 方法 / Auto-collects all @task methods
            process=Process.sequential,   # 顺序执行：Task 1 → 2 → 3 → 4 → 5 → 6
            verbose=True,
            max_rpm=6,                    # API 限速，避免触发 DeepSeek 频率限制 / Rate limit for DeepSeek API
            task_callback=self.task_callback,  # 前端实时进度回调 / Real-time frontend progress callback
        )
