from app.service.intent_detector.base_intent_detector import BaseIntentDetector, Intent


class LLMIntentDetector(BaseIntentDetector):
    async def detect(self, content: str) -> Intent:
        return "general"
