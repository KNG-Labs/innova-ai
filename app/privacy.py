from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any

import phonenumbers
import tldextract
from presidio_analyzer import (
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
)
from presidio_analyzer.nlp_engine import NoOpNlpEngine
from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer


class PiiKind(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    TELEGRAM = "telegram"


class PrivacyBoundaryError(RuntimeError):
    """Базовая ошибка локальной privacy boundary."""


class PiiAnalysisError(PrivacyBoundaryError):
    """Локальный анализ ПД не завершился надёжно."""


class PiiDetectedError(PrivacyBoundaryError):
    """Поддерживаемые ПД обнаружены на внешней границе."""

    def __init__(self, kinds: set[PiiKind]) -> None:
        self.kinds = frozenset(kinds)
        labels = ", ".join(sorted(kind.value for kind in kinds))
        super().__init__(f"Outbound payload contains supported PII: {labels}")


@dataclass(frozen=True)
class PiiEntity:
    kind: PiiKind
    raw: str
    normalized: str
    start: int
    end: int


@dataclass(frozen=True)
class SanitizedText:
    text: str
    contacts: dict[str, str]
    contact_only: bool


_ANALYZER_LANGUAGE = "en"
_PHONE_ENTITY = "PHONE_NUMBER"
_EMAIL_ENTITY = "EMAIL_ADDRESS"
_TELEGRAM_ENTITY = "TELEGRAM_USERNAME"
_SUPPORTED_ENTITIES = [_PHONE_ENTITY, _EMAIL_ENTITY, _TELEGRAM_ENTITY]
_ENTITY_KINDS = {
    _PHONE_ENTITY: PiiKind.PHONE,
    _EMAIL_ENTITY: PiiKind.EMAIL,
    _TELEGRAM_ENTITY: PiiKind.TELEGRAM,
}
_TELEGRAM_PATTERNS = [
    Pattern(
        name="telegram-handle",
        regex=r"(?<![\w@])@[A-Z][A-Z0-9_]{4,31}\b",
        score=0.8,
    ),
    Pattern(
        name="telegram-labeled",
        regex=(
            r"(?<=\b(?:telegram|телеграм|tg)\s*[:=-]?\s*)"
            r"[A-Z][A-Z0-9_]{4,31}\b"
        ),
        score=0.8,
    ),
]
_OFFLINE_TLD_EXTRACTOR = tldextract.TLDExtract(
    cache_dir=None,
    suffix_list_urls=(),
)
_EXPLICIT_NAME_PATTERN = re.compile(
    r"\b(?:меня\s+зовут|мо[её]\s+имя)\s+"
    r"[A-ZА-ЯЁ][A-ZА-ЯЁa-zа-яё-]{1,63}\b",
    re.IGNORECASE,
)
_CONTACT_ONLY_WORDS = {
    "call",
    "contact",
    "email",
    "mail",
    "me",
    "my",
    "phone",
    "telegram",
    "tg",
    "вам",
    "вот",
    "для",
    "звоните",
    "контакт",
    "контакты",
    "мне",
    "мой",
    "моя",
    "моё",
    "номер",
    "пишите",
    "по",
    "почта",
    "повтор",
    "связаться",
    "тел",
    "телеграм",
    "телефон",
    "это",
}


class _OfflineEmailRecognizer(EmailRecognizer):
    """EmailRecognizer с локальным snapshot public suffix list."""

    def validate_result(self, pattern_text: str) -> bool:
        return _OFFLINE_TLD_EXTRACTOR(pattern_text).fqdn != ""


@lru_cache(maxsize=1)
def get_pii_analyzer() -> AnalyzerEngine:
    """Создать единственный локальный AnalyzerEngine с явным registry."""

    try:
        registry = RecognizerRegistry(
            recognizers=[
                PhoneRecognizer(supported_regions=["RU"]),
                _OfflineEmailRecognizer(),
                PatternRecognizer(
                    supported_entity=_TELEGRAM_ENTITY,
                    patterns=_TELEGRAM_PATTERNS,
                ),
            ],
            supported_languages=[_ANALYZER_LANGUAGE],
        )
        analyzer = AnalyzerEngine(
            registry=registry,
            nlp_engine=NoOpNlpEngine(
                models=[{"lang_code": _ANALYZER_LANGUAGE, "model_name": ""}]
            ),
            supported_languages=[_ANALYZER_LANGUAGE],
        )
        smoke_text = "startup@example.com +7 999 123-45-67 @startup_user"
        detected = {
            result.entity_type
            for result in analyzer.analyze(
                text=smoke_text,
                language=_ANALYZER_LANGUAGE,
                entities=_SUPPORTED_ENTITIES,
            )
        }
        if detected != set(_SUPPORTED_ENTITIES):
            missing = ", ".join(sorted(set(_SUPPORTED_ENTITIES) - detected))
            raise RuntimeError(f"recognizers failed startup smoke check: {missing}")
        return analyzer
    except Exception as exc:
        raise PiiAnalysisError("Failed to initialize local PII analyzer") from exc


def initialize_pii_analyzer() -> None:
    """Явно прогреть локальный analyzer при старте приложения."""

    get_pii_analyzer()


class PiiSanitizer:
    """Локально извлекает и псевдонимизирует поддерживаемые контактные ПД.

    Экземпляр создаётся на один запрос/диалоговый контекст. Карты токенов внутри
    экземпляра гарантируют, что одинаковое значение получает одинаковый токен.
    """

    def __init__(self, analyzer: AnalyzerEngine | None = None) -> None:
        self._analyzer = analyzer if analyzer is not None else get_pii_analyzer()
        self._tokens: dict[PiiKind, dict[str, str]] = {kind: {} for kind in PiiKind}

    def seed_contacts(self, contact: dict[str, Any] | None) -> None:
        """Зарегистрировать уже сохранённые контакты для стабильных токенов."""

        for kind in PiiKind:
            value = (contact or {}).get(kind.value)
            if isinstance(value, str) and value.strip():
                normalized = self._normalize(kind, value)
                self._token_for(kind, normalized)

    def sanitize_text(self, text: str) -> SanitizedText:
        entities = self.find_entities(text)
        contacts: dict[str, str] = {}
        parts: list[str] = []
        cursor = 0

        for entity in entities:
            parts.append(text[cursor : entity.start])
            parts.append(self._token_for(entity.kind, entity.normalized))
            contacts[entity.kind.value] = entity.normalized
            cursor = entity.end

        parts.append(text[cursor:])
        return SanitizedText(
            text="".join(parts),
            contacts=contacts,
            contact_only=bool(entities) and self._is_contact_only(text, entities),
        )

    def sanitize_value(self, value: Any) -> Any:
        """Рекурсивно очистить строки в JSON-подобной структуре."""

        if isinstance(value, str):
            return self.sanitize_text(value).text
        if isinstance(value, dict):
            return {key: self.sanitize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.sanitize_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.sanitize_value(item) for item in value)
        return value

    @classmethod
    def ensure_safe(cls, value: Any) -> None:
        """Fail-closed проверка непосредственно перед внешним вызовом."""

        detected: set[PiiKind] = set()
        scanner = cls()
        for text in cls._iter_strings(value):
            detected.update(entity.kind for entity in scanner.find_entities(text))
        if detected:
            raise PiiDetectedError(detected)

    def find_entities(self, text: str) -> tuple[PiiEntity, ...]:
        try:
            results = self._analyzer.analyze(
                text=text,
                language=_ANALYZER_LANGUAGE,
                entities=_SUPPORTED_ENTITIES,
            )
        except PrivacyBoundaryError:
            raise
        except Exception as exc:
            raise PiiAnalysisError("Local PII analysis failed") from exc

        candidates: list[PiiEntity] = []
        for result in results:
            kind = _ENTITY_KINDS.get(result.entity_type)
            if kind is None:
                continue
            raw = text[result.start : result.end]
            candidates.append(
                PiiEntity(
                    kind=kind,
                    raw=raw,
                    normalized=self._normalize(kind, raw),
                    start=result.start,
                    end=result.end,
                )
            )

        priority = {
            PiiKind.EMAIL: 0,
            PiiKind.TELEGRAM: 1,
            PiiKind.PHONE: 2,
        }
        accepted: list[PiiEntity] = []
        for candidate in sorted(
            candidates,
            key=lambda item: (item.start, priority[item.kind], -item.end),
        ):
            if any(
                candidate.start < current.end and current.start < candidate.end
                for current in accepted
            ):
                continue
            accepted.append(candidate)
        return tuple(sorted(accepted, key=lambda item: item.start))

    def _token_for(self, kind: PiiKind, normalized: str) -> str:
        tokens = self._tokens[kind]
        if normalized not in tokens:
            tokens[normalized] = f"[{kind.value.upper()}_{len(tokens) + 1}]"
        return tokens[normalized]

    @staticmethod
    def _normalize(kind: PiiKind, value: str) -> str:
        if kind == PiiKind.PHONE:
            return PiiSanitizer._normalize_phone(value)
        if kind == PiiKind.EMAIL:
            return value.strip().casefold()
        return f"@{value.strip().lstrip('@').casefold()}"

    @staticmethod
    def _normalize_phone(value: str) -> str:
        try:
            phone = phonenumbers.parse(value, "RU")
        except phonenumbers.NumberParseException as exc:
            raise PiiAnalysisError(
                "Recognized phone number could not be normalized"
            ) from exc
        if not phonenumbers.is_valid_number(phone):
            raise PiiAnalysisError("Recognized phone number failed validation")
        return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164)

    @staticmethod
    def _iter_strings(value: Any) -> Iterator[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                if isinstance(key, str):
                    yield key
                yield from PiiSanitizer._iter_strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from PiiSanitizer._iter_strings(item)

    @staticmethod
    def _is_contact_only(text: str, entities: tuple[PiiEntity, ...]) -> bool:
        parts: list[str] = []
        cursor = 0
        for entity in entities:
            parts.append(text[cursor : entity.start])
            cursor = entity.end
        parts.append(text[cursor:])
        residual = _EXPLICIT_NAME_PATTERN.sub(" ", "".join(parts))
        words = {word.casefold() for word in re.findall(r"[A-ZА-ЯЁa-zа-яё]+", residual)}
        return words.issubset(_CONTACT_ONLY_WORDS)
