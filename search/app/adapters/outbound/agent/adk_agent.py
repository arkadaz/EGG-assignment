from collections.abc import Awaitable, Callable
from uuid import uuid4

from google.adk.agents import LlmAgent, RunConfig
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.application.ports.agent import AgentPort
from app.application.prompts import AGENT_PROMPT


class AdkAgent(AgentPort):
    def __init__(
        self,
        model: str,
        fallback_model: str,
        api_key: str,
        reasoning_effort: str,
        max_llm_calls: int,
    ) -> None:
        self._model = LiteLlm(
            model=model,
            fallbacks=[fallback_model],
            api_key=api_key,
            reasoning_effort=reasoning_effort,
            drop_params=True,
        )
        self._max_llm_calls = max_llm_calls

    def build(self, tools: list[Callable[..., Awaitable]]) -> LlmAgent:
        return LlmAgent(
            name="knowledge_agent",
            model=self._model,
            instruction=AGENT_PROMPT,
            tools=tools,
        )

    async def run(self, question: str, tools: list[Callable[..., Awaitable]]) -> str:
        runner = Runner(
            agent=self.build(tools),
            app_name="egg-rag",
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )
        message = types.Content(role="user", parts=[types.Part(text=question)])
        run_config = RunConfig(max_llm_calls=self._max_llm_calls)

        answer = ""
        async for event in runner.run_async(
            user_id="api", session_id=str(uuid4()), new_message=message, run_config=run_config
        ):
            if event.is_final_response() and event.content and event.content.parts:
                answer = final_text(event.content.parts)
        return answer


def final_text(parts: list[types.Part]) -> str:
    texts = []
    for part in parts:
        if part.text and not part.thought:
            texts.append(part.text)
    return "".join(texts)
