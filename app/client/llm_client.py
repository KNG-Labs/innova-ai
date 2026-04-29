from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMReply:
    text: str
    intent: str


class LLMClient(Protocol):
    async def generate_reply(self, text: str) -> LLMReply: ...


class StubLLMClient:
    async def generate_reply(self, text: str) -> LLMReply:
        return LLMReply(
            text="Здравствуйте! Чем могу помочь?",
            intent="greeting",
        )
