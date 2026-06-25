from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import ArxivPaperTool, SerperDevTool

from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS


def _check_report_structure(output):
    """Verify the final report contains all required section headings."""
    missing = [h for h in _REQUIRED_REPORT_HEADINGS if h not in output.raw]
    if missing:
        return False, "Missing required headings:\n- " + "\n- ".join(missing)
    return True, output


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
            config=self.agents_config["market_intelligence_analyst"],  # type: ignore[index]
            tools=[SerperDevTool()],
            verbose=True,
            inject_date=True,
        )

    @agent
    def commercialization_report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["commercialization_report_writer"],  # type: ignore[index]
            verbose=True,
        )

    @task
    def academic_research_task(self) -> Task:
        return Task(
            config=self.tasks_config["academic_research_task"],  # type: ignore[index]
        )

    @task
    def patent_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["patent_analysis_task"],  # type: ignore[index]
        )

    @task
    def market_intelligence_task(self) -> Task:
        return Task(
            config=self.tasks_config["market_intelligence_task"],  # type: ignore[index]
        )

    @task
    def commercialization_report_task(self) -> Task:
        return Task(
            config=self.tasks_config["commercialization_report_task"],  # type: ignore[index]
            guardrail=_check_report_structure,
            guardrail_max_retries=2,
        )

    @crew
    def crew(self) -> Crew:
        """Create the academic commercialization assessment crew."""

        all_tasks = self.tasks
        context_tasks = all_tasks[:-1]   # academic, patent, market
        report_task = all_tasks[-1]      # commercialization_report
        report_task.context = context_tasks

        return Crew(
            agents=self.agents,
            tasks=all_tasks,
            process=Process.sequential,
            verbose=True,
            max_rpm=6,
        )
