from google.adk.agents import BaseAgent
from google.adk.cli.utils.base_agent_loader import BaseAgentLoader


class SingleAgentLoader(BaseAgentLoader):
    def __init__(self) -> None:
        self.agent: BaseAgent | None = None

    def load_agent(self, agent_name: str) -> BaseAgent | None:
        return self.agent

    def list_agents(self) -> list[str]:
        if self.agent is None:
            return []
        return [self.agent.name]
