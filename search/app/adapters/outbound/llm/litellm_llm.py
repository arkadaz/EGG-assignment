import litellm

from app.application.ports.llm import LLMPort
from app.application.prompts import ANSWER_PROMPT, answer_user_message
from app.domain.models import Passage

litellm.suppress_debug_info = True
litellm.drop_params = True


class LiteLLMAdapter(LLMPort):
    def __init__(
        self, model: str, fallback_model: str, api_key: str, reasoning_effort: str
    ) -> None:
        self._model = model
        self._fallback_model = fallback_model
        self._api_key = api_key
        self._reasoning_effort = reasoning_effort

    async def generate(self, question: str, context: list[Passage]) -> str:
        response = await litellm.acompletion(
            model=self._model,
            fallbacks=[self._fallback_model],
            api_key=self._api_key,
            reasoning_effort=self._reasoning_effort,
            messages=[
                {"role": "system", "content": ANSWER_PROMPT},
                {"role": "user", "content": answer_user_message(question, context)},
            ],
        )
        return response.choices[0].message.content
