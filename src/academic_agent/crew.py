# ============================================================
# ORIGINAL DEMO: LatestAiDevelopmentCrew with 2 agents
#
# MODIFIED: Academic commercialization assessment with:
#   - 4 specialized agents and tasks
#   - Structured EvidenceReport outputs for research tasks
#   - Source-specific guardrails with automatic retries
#   - Citation-integrity guardrail on the final report
#   - Explicit context wiring and API rate limiting
# ============================================================

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import ArxivPaperTool, SerperDevTool

from academic_agent.evidence import (
    EvidenceReport,
    make_final_report_guardrail,
    validate_academic_evidence,
    validate_market_evidence,
    validate_patent_evidence,
)


@CrewBase
class AcademicAgent:
    """Academic Commercialization Assessment Crew."""

    agents: list[BaseAgent]
    tasks: list[Task]

    @agent
    def academic_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["academic_researcher"],  # type: ignore[index]
            tools=[ArxivPaperTool(), SerperDevTool()],
            verbose=True,
            inject_date=True,
        )

    @agent
    def patent_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["patent_analyst"],  # type: ignore[index]
            tools=[SerperDevTool()],
            verbose=True,
            inject_date=True,
        )

    @agent
    def market_intelligence_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config[
                "market_intelligence_analyst"
            ],  # type: ignore[index]
            tools=[SerperDevTool()],
            verbose=True,
            inject_date=True,
        )

    @agent
    def commercialization_report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config[
                "commercialization_report_writer"
            ],  # type: ignore[index]
            verbose=True,
        )

    @task
    def academic_research_task(self) -> Task:
        return Task(
            config=self.tasks_config["academic_research_task"],  # type: ignore[index]
            output_pydantic=EvidenceReport,
            guardrail=validate_academic_evidence,
            guardrail_max_retries=2,
        )

    @task
    def patent_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["patent_analysis_task"],  # type: ignore[index]
            output_pydantic=EvidenceReport,
            guardrail=validate_patent_evidence,
            guardrail_max_retries=2,
        )

    @task
    def market_intelligence_task(self) -> Task:
        return Task(
            config=self.tasks_config[
                "market_intelligence_task"
            ],  # type: ignore[index]
            output_pydantic=EvidenceReport,
            guardrail=validate_market_evidence,
            guardrail_max_retries=2,
        )

    @task
    def commercialization_report_task(self) -> Task:
        context_tasks = [
            self.academic_research_task(),
            self.patent_analysis_task(),
            self.market_intelligence_task(),
        ]
        return Task(
            config=self.tasks_config[
                "commercialization_report_task"
            ],  # type: ignore[index]
            context=context_tasks,
            guardrail=make_final_report_guardrail(context_tasks),
            guardrail_max_retries=2,
            markdown=True,
        )

    @crew
    def crew(self) -> Crew:
        """Create the academic commercialization assessment crew."""

        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            max_rpm=6,
        )
