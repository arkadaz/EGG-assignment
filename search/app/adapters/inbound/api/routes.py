from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.application.ask_agent import AskAgent
from app.application.ask_question import AskQuestion
from app.domain.models import Answer

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


def get_ask_question(request: Request) -> AskQuestion:
    return request.app.state.ask_question


def get_ask_agent(request: Request) -> AskAgent:
    if request.app.state.ask_agent is None:
        raise HTTPException(status_code=503, detail="The agent needs an LLM_API key")
    return request.app.state.ask_agent


@router.post("/ask")
async def ask(
    body: AskRequest, ask_question: Annotated[AskQuestion, Depends(get_ask_question)]
) -> Answer:
    return await ask_question.ask(body.question)


@router.post("/agent/ask")
async def ask_agent(
    body: AskRequest, ask_agent: Annotated[AskAgent, Depends(get_ask_agent)]
) -> Answer:
    return await ask_agent.ask(body.question)
