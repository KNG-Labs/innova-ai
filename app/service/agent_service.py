from sqlalchemy.ext.asyncio import AsyncSession

from app.client.llm_client import LLMClient
from app.repository.dialog_session_repository import DialogSessionRepository
from app.repository.message_repository import MessageRepository
from app.repository.user_repository import UserRepository
from app.schemas.agent_schema import (
    AgentMessageRequest,
    AgentMessageResponse,
    DialogState,
)
from app.schemas.openai_schema import (
    AssistantMessage,
    ChatCompletionRequest,
    UserMessage,
)
from app.service.business_service import MessageNormalizer, DialogPolicy
from app.service.intent_detector.base_intent_detector import BaseIntentDetector


class AgentService:
    def __init__(
        self,
        *,
        db_session: AsyncSession,
        llm_client: LLMClient,
        normalizer: MessageNormalizer,
        intent_detector: BaseIntentDetector,
        dialog_policy: DialogPolicy,
    ) -> None:

        self._db_session = db_session
        self._llm_client = llm_client
        self._normalizer = normalizer
        self._intent_detector = intent_detector
        self._dialog_policy = dialog_policy

        self._users = UserRepository(db_session)
        self._sessions = DialogSessionRepository(db_session)
        self._messages = MessageRepository(db_session)

    async def handle_message(
        self, request: AgentMessageRequest
    ) -> AgentMessageResponse:

        normalized_content = self._normalizer.normalize(request.content)
        intent = await self._intent_detector.detect(normalized_content)
        next_step = self._dialog_policy.next_step_for(intent)

        user = await self._users.get_or_create_anonymous_user(
            channel=request.channel.value,
            anonymous_id=request.anonymous_id,
        )

        dialog_session = await self._sessions.get_or_create_active_session(
            user_id=user.id,
            session_id=request.session_id,
        )

        user_message = await self._messages.create(
            session_id=dialog_session.id,
            role="user",
            content=normalized_content,
            message_metadata={
                "intent": intent,
                "next_step": next_step,
            },
        )

        history = await self._messages.list_recent_messages(
            dialog_session.id,
            limit=20)
        llm_request = self._build_llm_request(history)

        llm_response = await self._llm_client.create_chat_completion(llm_request)
        answer = self._extract_answer(llm_response)

        assistant_message = await self._messages.create(
            session_id=dialog_session.id,
            role="assistant",
            content=answer,
            message_metadata={
                "intent": intent,
                "next_step": next_step,
            },
        )

        await self._db_session.commit()

        return AgentMessageResponse(
            user_id=user.id,
            session_id=dialog_session.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            answer=answer,
            state=DialogState(dialog_session.state),
            intent=intent,
            next_step=next_step,
        )

    @staticmethod
    def _build_llm_request(history) -> ChatCompletionRequest:
        messages = []

        for message in history:
            if message.role == "user":
                messages.append(UserMessage(content=message.content))
            elif message.role == "assistant":
                messages.append(AssistantMessage(content=message.content))

        return ChatCompletionRequest(
            messages=messages,
        )

    @staticmethod
    def _extract_answer(llm_response) -> str:
        if not llm_response.choices:
            return "Извините, сейчас не удалось сформировать ответ."

        content = llm_response.choices[0].message.content

        if not content:
            return "Извините, сейчас не удалось сформировать ответ."

        return content
