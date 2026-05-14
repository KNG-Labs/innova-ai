from abc import ABC, abstractmethod
from typing import Literal

Intent = Literal["support", "general", "lead_request", "pricing"]


class BaseIntentDetector(ABC):
    @abstractmethod
    async def detect(self, content: str) -> Intent:
        pass
