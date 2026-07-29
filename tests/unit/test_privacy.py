import pytest

from app.privacy import PiiAnalysisError, PiiDetectedError, PiiSanitizer

pytestmark = pytest.mark.unit


def test_sanitizer_extracts_contacts_and_reuses_stable_tokens() -> None:
    sanitizer = PiiSanitizer()

    result = sanitizer.sanitize_text(
        "Телефон +7 (999) 123-45-67, повтор +79991234567, "
        "email User@Example.COM, Telegram @ivan_auto"
    )

    assert result.text == (
        "Телефон [PHONE_1], повтор [PHONE_1], email [EMAIL_1], Telegram [TELEGRAM_1]"
    )
    assert result.contacts == {
        "phone": "+79991234567",
        "email": "user@example.com",
        "telegram": "@ivan_auto",
    }
    assert result.contact_only is True


@pytest.mark.parametrize(
    "text",
    [
        "Мой телефон: 8 999 123-45-67",
        "Email: user@example.com",
        "Telegram: ivan_auto",
        "Телефон +79991234567, меня зовут Иван",
    ],
)
def test_contact_only_detection(text: str) -> None:
    assert PiiSanitizer().sanitize_text(text).contact_only is True


def test_mixed_message_is_not_contact_only() -> None:
    result = PiiSanitizer().sanitize_text("Хочу купить Camry, телефон +79991234567")

    assert result.text == "Хочу купить Camry, телефон [PHONE_1]"
    assert result.contact_only is False


def test_fail_closed_guard_rejects_supported_pii_but_accepts_tokens() -> None:
    with pytest.raises(PiiDetectedError) as exc_info:
        PiiSanitizer.ensure_safe(
            {
                "messages": [
                    {"content": ("Пишите на user@example.com или +7 999 123-45-67")}
                ]
            }
        )

    assert exc_info.value.kinds
    PiiSanitizer.ensure_safe(
        {"messages": [{"content": "Пишите на [EMAIL_1] или [PHONE_1]"}]}
    )


def test_seeded_contact_keeps_first_token_across_new_context() -> None:
    sanitizer = PiiSanitizer()
    sanitizer.seed_contacts({"phone": "+79991234567"})

    result = sanitizer.sanitize_text("Старый номер +79991234567")

    assert result.text == "Старый номер [PHONE_1]"


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("Позвоните 999 123-45-67", "+79991234567"),
        ("US office: +1 415 555 2671", "+14155552671"),
        ("UK office: +44 20 7946 0958", "+442079460958"),
    ],
)
def test_valid_ru_and_international_phones_use_e164(
    text: str,
    normalized: str,
) -> None:
    result = PiiSanitizer().sanitize_text(text)

    assert result.contacts["phone"] == normalized
    assert "[PHONE_1]" in result.text


@pytest.mark.parametrize(
    "text",
    [
        "Номер заказа 123456789012",
        "Дата 29.07.2026 и код 1234567890",
        "Заказ 1234567890 от 2026-07-29",
    ],
)
def test_order_numbers_and_digits_near_dates_are_not_phones(text: str) -> None:
    result = PiiSanitizer().sanitize_text(text)

    assert result.text == text
    assert result.contacts == {}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Telegram @Ivan_Auto", "Telegram [TELEGRAM_1]"),
        ("Telegram: Ivan_Auto", "Telegram: [TELEGRAM_1]"),
    ],
)
def test_telegram_handle_formats(text: str, expected: str) -> None:
    result = PiiSanitizer().sanitize_text(text)

    assert result.text == expected
    assert result.contacts == {"telegram": "@ivan_auto"}


def test_recursive_payload_sanitization_reuses_seeded_tokens() -> None:
    sanitizer = PiiSanitizer()
    sanitizer.seed_contacts(
        {
            "phone": "+79991234567",
            "email": "user@example.com",
            "telegram": "@ivan_auto",
        }
    )

    safe = sanitizer.sanitize_value(
        {
            "current": "Телефон 8 999 123-45-67",
            "history": [
                "user@example.com",
                {"contact": "Telegram: ivan_auto"},
            ],
        }
    )

    assert safe == {
        "current": "Телефон [PHONE_1]",
        "history": ["[EMAIL_1]", {"contact": "Telegram: [TELEGRAM_1]"}],
    }


def test_analyzer_failure_is_wrapped_as_privacy_boundary_error() -> None:
    class _FailingAnalyzer:
        def analyze(self, **kwargs):
            raise RuntimeError("synthetic analyzer failure")

    sanitizer = PiiSanitizer(analyzer=_FailingAnalyzer())  # type: ignore[arg-type]

    with pytest.raises(PiiAnalysisError):
        sanitizer.sanitize_text("user@example.com")
