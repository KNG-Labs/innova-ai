from app.service.intent_detector.base_intent_detector import BaseIntentDetector, Intent


class KeywordIntentDetector(BaseIntentDetector):
    """Класс для Определения намерения пользователя"""

    _lead_keywords = ("заявк", "консультац", "связ", "оставить контакт", "купить")
    _pricing_keywords = ("цен", "стоим", "прайс", "тариф", "сколько")
    _support_keywords = ("ошибк", "не работает", "проблем", "помогите", "support")

    async def detect(self, content: str) -> Intent:
        lowered = content.lower()

        if any(keyword in lowered for keyword in self._pricing_keywords):
            return "pricing"
        if any(keyword in lowered for keyword in self._lead_keywords):
            return "lead_request"
        if any(keyword in lowered for keyword in self._support_keywords):
            return "support"
        return "general"
