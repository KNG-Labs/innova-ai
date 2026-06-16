from sqlalchemy.ext.asyncio import AsyncSession

from app.client.ag2_agent_client import Ag2AgentClient, AgentDecision
from app.client.llm_client import LLMClient
from app.repository import LeadRepository
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
from app.service.state_machine import resolve_next_state


class AgentService:
    def __init__(
        self,
        *,
        db_session: AsyncSession,
        ag2_client: Ag2AgentClient,
        normalizer: MessageNormalizer,
    ) -> None:

        self._db_session = db_session
        self._ag2_client = ag2_client
        self._normalizer = normalizer

        self._users = UserRepository(db_session)
        self._sessions = DialogSessionRepository(db_session)
        self._messages = MessageRepository(db_session)
        self._leads = LeadRepository(db_session)

    async def handle_message(
        self, request: AgentMessageRequest
    ) -> AgentMessageResponse:

        content = self._normalizer.normalize(request.content)

        user = await self._users.get_or_create_anonymous_user(
            channel=request.channel.value,
            anonymous_id=request.anonymous_id,
        )

        session = await self._sessions.get_or_create_active_session(
            user_id=user.id,
            session_id=request.session_id,
        )

        current_state = DialogState(session.state)

        # Загрузить текущий draft лида для контекста
        lead = await self._leads.get_by_session_id(session.id)
        qualification_data = lead.qualification if lead and lead.qualification else {}

        # История для AG2 (последние 20 сообщений)
        history_rows = await self._messages.list_recent_messages(session.id, limit=20)
        history = [
            {"role": m.role, "content": m.content}
            for m in history_rows
        ]

        # Сохранение входящего сообщения
        user_message = await self._messages.create(
            session_id=session.id,
            role="user",
            content=content,
        )

        # Вызов AG2
        decision: AgentDecision = await self._ag2_client.decide(
            user_message=content,
            history=history,
            current_state=current_state.value,
            qualification_data=qualification_data,
        )

        # Детерминированный переход состояния
        next_state = resolve_next_state(current_state, decision)

        # Обновить qualification_data
        merged_qualification_data = {**qualification_data, **decision.qualification_data}
        # Убрать None-значения которые перезаписали бы реальные данные
        merged_qual = {k: v for k, v in merged_qualification_data.items() if v is not None}


        # Сохранение ответа ассистента
        assistant_message = await self._messages.create(
            session_id=session.id,
            role="assistant",
            content=decision.answer,
        )

        # Обновить состояние сессии
        await self._sessions.update_state(session.id, next_state.value)

        # Создать или обновить draft лида
        lead = await self._leads.upsert_draft(
            user_id=user.id,
            session_id=session.id,
            qualification=merged_qual,
            summary=decision.lead_summary,
        )

        await self._db_session.commit()

        return AgentMessageResponse(
            user_id=user.id,
            session_id=session.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            answer=decision.answer,
            state=next_state,
            intent=decision.intent,
            next_step=next_state.value,
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
