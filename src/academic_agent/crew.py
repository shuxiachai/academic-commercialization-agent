# ============================================================
# ORIGINAL DEMO: LatestAiDevelopmentCrew with 2 agents
#   - researcher (SerperDevTool only)
#   - reporting_analyst (no tools)
#   2 tasks: research_task → reporting_task
#
# MODIFIED: Replaced with AcademicAgent — 4 specialized agents
#   for academic research commercialization assessment.
#   Changes vs original:
#   - 4 agents instead of 2 (added patent_analyst,
#     market_intelligence_analyst, commercialization_report_writer)
#   - 4 tasks instead of 2, executed sequentially
#   - Added ArxivPaperTool to academic_researcher
#   - Added inject_date=True on research agents
#   - Added guardrail on final report task
#   - Explicit context wiring: first 3 tasks feed into report task
#   - Added max_rpm=6 to stay within API rate limits
#   - Added evidence.py import for report structure validation
# ============================================================

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import ArxivPaperTool, SerperDevTool  # MODIFIED: added ArxivPaperTool

from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS  # ADDED


# ADDED: guardrail function — validates final report has all required headings
def _check_report_structure(output):
    missing = [h for h in _REQUIRED_REPORT_HEADINGS if h not in output.raw]
    if missing:
        return False, "Missing required headings:\n- " + "\n- ".join(missing)
    return True, output


@CrewBase
class AcademicAgent:  # MODIFIED: renamed from LatestAiDevelopmentCrew
    """Academic Commercialization Assessment Crew."""

    agents: list[BaseAgent]
    tasks: list[Task]

    # ----------------------------------------------------------
    # AGENTS — original had: researcher, reporting_analyst
    # MODIFIED: replaced with 4 domain-specific agents
    # ----------------------------------------------------------

    @agent
    def academic_researcher(self) -> Agent:  # MODIFIED: was researcher
        return Agent(
            config=self.agents_config["academic_researcher"],  # type: ignore[index]
            tools=[ArxivPaperTool(), SerperDevTool()],  # MODIFIED: added ArxivPaperTool
            verbose=True,
            inject_date=True,  # ADDED
        )

    @agent
    def patent_analyst(self) -> Agent:  # ADDED
        return Agent(
            config=self.agents_config["patent_analyst"],  # type: ignore[index]
            tools=[SerperDevTool()],
            verbose=True,
            inject_date=True,
        )

    @agent
    def market_intelligence_analyst(self) -> Agent:  # ADDED
        return Agent(
            config=self.agents_config["market_intelligence_analyst"],  # type: ignore[index]
            tools=[SerperDevTool()],
            verbose=True,
            inject_date=True,
        )

    @agent
    def commercialization_report_writer(self) -> Agent:  # MODIFIED: was reporting_analyst
        return Agent(
            config=self.agents_config["commercialization_report_writer"],  # type: ignore[index]
            verbose=True,
        )

    # ----------------------------------------------------------
    # TASKS — original had: research_task, reporting_task
    # MODIFIED: replaced with 4 tasks matching the 4 agents
    # ----------------------------------------------------------

    @task
    def academic_research_task(self) -> Task:  # MODIFIED: was research_task
        return Task(
            config=self.tasks_config["academic_research_task"],  # type: ignore[index]
        )

    @task
    def patent_analysis_task(self) -> Task:  # ADDED
        return Task(
            config=self.tasks_config["patent_analysis_task"],  # type: ignore[index]
        )

    @task
    def market_intelligence_task(self) -> Task:  # ADDED
        return Task(
            config=self.tasks_config["market_intelligence_task"],  # type: ignore[index]
        )

    @task
    def commercialization_report_task(self) -> Task:  # MODIFIED: was reporting_task
        return Task(
            config=self.tasks_config["commercialization_report_task"],  # type: ignore[index]
            guardrail=_check_report_structure,   # ADDED: validates report structure
            guardrail_max_retries=2,             # ADDED
        )

    # ----------------------------------------------------------
    # CREW — MODIFIED: explicit context wiring + max_rpm
    # ----------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        """Create the academic commercialization assessment crew."""

        # ADDED: wire first 3 tasks as context for the report task
        all_tasks = self.tasks
        context_tasks = all_tasks[:-1]   # academic, patent, market
        report_task = all_tasks[-1]      # commercialization_report
        report_task.context = context_tasks

        return Crew(
            agents=self.agents,
            tasks=all_tasks,
            process=Process.sequential,
            verbose=True,
            max_rpm=6,  # ADDED: rate limiting for DeepSeek API
        )
