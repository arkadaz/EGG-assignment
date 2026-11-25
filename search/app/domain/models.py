from dataclasses import dataclass


@dataclass(frozen=True)
class Passage:
    title: str
    source: str
    content: str
    score: float


@dataclass(frozen=True)
class Answer:
    answer: str
    sources: list[Passage]
    prompt_version: str
    session_id: str | None = None
