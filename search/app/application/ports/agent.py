from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class AgentPort(ABC):
    @abstractmethod
    async def run(self, question: str, tools: list[Callable[..., Awaitable]]) -> str: ...
