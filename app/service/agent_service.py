from sqlalchemy.ext.asyncio import AsyncSession

from app.client.ag2_agent_client import Ag2AgentClient
from app.repository import LeadRepository
from app.repository.dialog_session_repository import DialogSessionRepository
from app.repository.message_repository import MessageRepository
from app.repository.user_repository import UserRepository
from app.schemas.agent_schema import (
    AgentMessageRequest,
    AgentMessageResponse,
    DialogState,
    AgentDecision,
)
from app.schemas.openai_schema import (
    AssistantMessage,
    ChatCompletionRequest,
    UserMessage,
)
from app.service.business_service import MessageNormalizer
from app.service.state_machine import resolve_next_state, is_lead_ready


class AgentService:
    def __init__(
        self,
        *,
        db_session: AsyncSession,
        llm_client: Ag2AgentClient,
        normalizer: MessageNormalizer,
    ) -> None:

        self._db_session = db_session
        self._llm_client = llm_client
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
        current_contact = lead.contact if lead and lead.contact else {}

        # История для AG2 (последние 20 сообщений)
        history_rows = await self._messages.list_recent_messages(session.id, limit=20)
        history = [{"role": m.role, "content": m.content} for m in history_rows]

        # Сохранение входящего сообщения
        user_message = await self._messages.create(
            session_id=session.id,
            role="user",
            content=content,
        )

        # Вызов AG2
        decision: AgentDecision = await self._llm_client.decide(
            user_message=content,
            history=history,
            current_state=current_state.value,
            qualification_data=qualification_data,
        )

        # Детерминированный переход состояния
        next_state = resolve_next_state(current_state, decision)

        # Обновить qualification_data
        merged_qualification_data = {
            **qualification_data,
            **decision.qualification_data,
        }
        # Убрать None-значения которые перезаписали бы реальные данные
        merged_qual = {
            k: v for k, v in merged_qualification_data.items() if v is not None
        }

        # Merge contact (не перезаписывать None поверх реальных данных)
        extracted_contact = decision.extracted_contact or {}
        merged_contact = {**current_contact, **extracted_contact}
        merged_contact = {k: v for k, v in merged_contact.items() if v is not None}
        # None если пустой dict (нет данных)
        final_contact = merged_contact if merged_contact else None

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
            contact=final_contact,
            summary=decision.lead_summary,
        )

        if next_state == DialogState.LEAD_READY and is_lead_ready(
            merged_qual, final_contact
        ):
            await self._leads.update(lead, status="ready")

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
