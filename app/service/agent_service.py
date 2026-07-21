import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.client.ag2_agent_client import Ag2AgentClient
from app.client.queue_client import QueueClient
from app.repository import LeadRepository
from app.repository.dialog_session_repository import DialogSessionRepository
from app.repository.message_repository import MessageRepository
from app.repository.user_repository import UserRepository
from app.schemas.agent_schema import (
    AgentMessageRequest,
    AgentMessageResponse,
    ContactPreference,
    DialogState,
    AgentDecision,
)
from app.service.business_service import MessageNormalizer
from app.service.knowledge_retrieval_service import (
    KnowledgeRetrievalService,
    format_chunks_for_prompt,
)
from app.service.state_machine import (
    resolve_next_state,
    is_lead_ready,
    is_contact_valid,
    apply_qualification_patch,
    merge_contact,
    compute_missing_fields,
    should_opt_out_after_contact_refusals,
)

_logger = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self,
        *,
        db_session: AsyncSession,
        llm_client: Ag2AgentClient,
        normalizer: MessageNormalizer,
        queue_client: QueueClient,
        delivery_provider: str,
        retrieval: KnowledgeRetrievalService,
    ) -> None:

        self._db_session = db_session
        self._llm_client = llm_client
        self._normalizer = normalizer
        self._queue = queue_client
        self._delivery_provider = delivery_provider
        self._retrieval = retrieval

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
        current_missing_fields = compute_missing_fields(
            qualification_data,
            current_contact or None,
        )
        contact_opt_out = session.contact_opt_out

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
        # RAG: retrieved context перед LLM
        retrieved = await self._retrieval.retrieve(content)
        retrieved_context = format_chunks_for_prompt(retrieved)

        decision: AgentDecision = await self._llm_client.decide(
            user_message=content,
            history=history,
            current_state=current_state.value,
            qualification_data=qualification_data,
            retrieved_context=retrieved_context,
            page_title=request.page_title,
            missing_fields=current_missing_fields,
            contact_opt_out=contact_opt_out,
        )

        # Слить данные ДО решения о переходе (backend - источник истины)
        merged_qual = apply_qualification_patch(
            qualification_data, decision.qualification_patch
        )
        merged_contact = merge_contact(current_contact, decision.extracted_contact)
        final_contact = merged_contact if merged_contact else None

        # Детерминированный переход по merged data
        next_state = resolve_next_state(
            current_state,
            decision,
            merged_qual,
            final_contact,
        )

        contact_refusals = session.contact_refusals
        contact_opt_in = (
            session.contact_opt_out
            and decision.contact_preference == ContactPreference.RESUME
        )
        if is_contact_valid(final_contact) or contact_opt_in:
            contact_refusals = 0
            contact_opt_out = False

        explicit_contact_refusal = (
            current_state == DialogState.CONTACT_CAPTURE
            and not is_contact_valid(final_contact)
            and decision.contact_preference == ContactPreference.REFUSAL
        )
        if explicit_contact_refusal:
            contact_refusals += 1
            if should_opt_out_after_contact_refusals(contact_refusals):
                contact_opt_out = True
                next_state = DialogState.FAQ
            else:
                next_state = DialogState.CONTACT_CAPTURE
        elif contact_opt_out:
            next_state = DialogState.FAQ

        # Сохранение ответа ассистента
        assistant_message = await self._messages.create(
            session_id=session.id,
            role="assistant",
            content=decision.answer,
        )

        # Определить, что сессия закрывается
        is_closing = (
            next_state in {DialogState.LEAD_READY, DialogState.CLOSED}
            and session.closed_at is None
        )
        # Обновить состояние сессии
        await self._sessions.update_state(
            session_id=session.id,
            state=next_state.value,
            contact_refusals=contact_refusals,
            contact_opt_out=contact_opt_out,
            close=is_closing,
        )

        # Создать или обновить draft лида
        lead = await self._leads.upsert_draft(
            user_id=user.id,
            session_id=session.id,
            qualification=merged_qual,
            contact=final_contact,
            summary=decision.lead_summary,
        )

        became_ready = False
        if next_state == DialogState.LEAD_READY and is_lead_ready(
            merged_qual, final_contact
        ):
            if lead.status == "draft":
                await self._leads.update(lead, status="ready")
                became_ready = True
            # уже ready/delivered/failed — статус не трогаем

        # у нового lead проставится id
        await self._db_session.flush()
        lead_id = lead.id

        missing_fields = compute_missing_fields(merged_qual, final_contact)

        await self._db_session.commit()

        if became_ready and self._delivery_provider != "disabled":
            try:
                await self._queue.enqueue_lead_delivery(
                    lead_id, self._delivery_provider
                )
            except Exception:
                _logger.warning(
                    "enqueue failed for lead %s; оставлен в 'ready', чинить ручным /deliver",
                    lead_id,
                    exc_info=True,
                )

        return AgentMessageResponse(
            user_id=user.id,
            session_id=session.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            answer=decision.answer,
            state=next_state,
            intent=decision.intent,
            next_step=next_state.value,
            missing_fields=missing_fields,
            lead_id=lead_id,
        )
