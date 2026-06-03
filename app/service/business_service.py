from __future__ import annotations

import re
from typing import Literal

from app.service.intent_detector.base_intent_detector import Intent

NextStep = Literal[
    "collect_contact",
    "send_pricing_summary",
    "ask_support_details",
    "continue_dialogue",
]

class DialogPolicy:
    """
    Бизнес-правила диалога.

    Сейчас класс отвечает только за выбор следующего шага по intent.
    Позже сюда можно будет постепенно перенести правила state machine.
    """

    @staticmethod
    def next_step_for(intent: Intent) -> NextStep:
        if intent == "lead_request":
            return "collect_contact"
        if intent == "pricing":
            return "send_pricing_summary"
        if intent == "support":
            return "ask_support_details"
        return "continue_dialogue"



class MessageNormalizer:
    """Нормализует текст входящего пользовательского сообщения."""

    @staticmethod
    def normalize(content: str) -> str:
        normalized = re.sub(r"\s+", " ", content).strip()

        if not normalized:
            raise ValueError("user message must not be empty")

        return normalized
