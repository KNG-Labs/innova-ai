from __future__ import annotations

import re


class MessageNormalizer:
    """Нормализует текст входящего пользовательского сообщения."""

    @staticmethod
    def normalize(content: str) -> str:
        normalized = re.sub(r"\s+", " ", content).strip()

        if not normalized:
            raise ValueError("user message must not be empty")

        return normalized
