import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.client.ag2_agent_client import LLMClient
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
    LeadIntentStatus,
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
    has_confirmed_lead_intent,
    has_explicit_lead_request,
    is_information_question,
    is_unknown_qualification_answer,
    next_expected_qualification_field,
)

_logger = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self,
        *,
        db_session: AsyncSession,
        llm_client: LLMClient,
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
        retrieved = await self._retrieval.retrieve(
            content,
            last_source_id=session.last_rag_source_id,
            last_source_title=session.last_rag_source_title,
            history=history,
        )
        retrieved_context = format_chunks_for_prompt(retrieved.chunks)

        decision: AgentDecision = await self._llm_client.decide(
            user_message=content,
            history=history,
            current_state=current_state.value,
            qualification_data=qualification_data,
            retrieved_context=retrieved_context,
            page_title=request.page_title,
            missing_fields=current_missing_fields,
            contact_opt_out=contact_opt_out,
            lead_intent_confirmation_pending=(session.lead_intent_confirmation_pending),
        )

        proposed_qualification_patch = dict(decision.qualification_patch)
        if (
            current_state == DialogState.QUALIFICATION
            and session.expected_qualification_field is not None
            and is_unknown_qualification_answer(content)
        ):
            proposed_qualification_patch[session.expected_qualification_field] = (
                "не указано"
            )

        decision_for_transition = decision.model_copy(
            update={"qualification_patch": proposed_qualification_patch}
        )
        lead_intent_confirmed = has_confirmed_lead_intent(
            current_state=current_state,
            user_message=content,
            decision=decision_for_transition,
            expected_qualification_field=session.expected_qualification_field,
            lead_intent_confirmation_pending=(session.lead_intent_confirmation_pending),
        )
        inline_qualification_faq = (
            current_state == DialogState.QUALIFICATION
            and retrieved.source_id is not None
            and is_information_question(content)
            and not has_explicit_lead_request(content)
            and not is_contact_valid(decision.extracted_contact)
        )
        rejected_qualification_start = (
            current_state in {DialogState.GREETING, DialogState.FAQ}
            and decision.next_state == DialogState.QUALIFICATION
            and not lead_intent_confirmed
        )
        if rejected_qualification_start:
            decision = await self._llm_client.decide(
                user_message=content,
                history=history,
                current_state=current_state.value,
                qualification_data=qualification_data,
                retrieved_context=retrieved_context,
                page_title=request.page_title,
                missing_fields=current_missing_fields,
                contact_opt_out=contact_opt_out,
                lead_intent_confirmation_pending=(
                    session.lead_intent_confirmation_pending
                ),
                force_lead_intent_confirmation=True,
            )
            if (
                decision.next_state != DialogState.FAQ
                or decision.lead_intent_status != LeadIntentStatus.NEEDS_CONFIRMATION
                or decision.qualification_patch
            ):
                decision = AgentDecision(
                    answer=(
                        "Уточните, пожалуйста: хотите, чтобы я помог подобрать "
                        "автомобиль для покупки?"
                    ),
                    intent="general",
                    next_state=DialogState.FAQ,
                    qualification_patch={},
                    missing_fields=current_missing_fields,
                    lead_ready=False,
                    lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
                )
            proposed_qualification_patch = {}
            lead_intent_confirmed = False
            inline_qualification_faq = False

        if inline_qualification_faq:
            expected_field = session.expected_qualification_field
            qualification_patch = (
                {
                    expected_field: proposed_qualification_patch[expected_field],
                }
                if expected_field is not None
                and expected_field in proposed_qualification_patch
                else {}
            )
        elif rejected_qualification_start:
            qualification_patch = {}
        else:
            qualification_patch = proposed_qualification_patch

        # Слить данные ДО решения о переходе (backend - источник истины)
        merged_qual = apply_qualification_patch(qualification_data, qualification_patch)
        merged_contact = merge_contact(current_contact, decision.extracted_contact)
        final_contact = merged_contact if merged_contact else None

        # Детерминированный переход по merged data
        next_state = resolve_next_state(
            current_state,
            decision,
            merged_qual,
            final_contact,
            lead_intent_confirmed=lead_intent_confirmed,
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

        lead_intent_confirmation_pending = (
            decision.lead_intent_status == LeadIntentStatus.NEEDS_CONFIRMATION
            and next_state == DialogState.FAQ
        )

        if inline_qualification_faq:
            next_state = DialogState.QUALIFICATION
        expected_qualification_field = next_expected_qualification_field(
            next_state,
            merged_qual,
        )

        last_rag_source_id = (
            retrieved.source_id
            if retrieved.source_id is not None
            else session.last_rag_source_id
        )
        last_rag_source_title = (
            retrieved.source_title
            if retrieved.source_id is not None
            else session.last_rag_source_title
        )

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
            lead_intent_confirmation_pending=lead_intent_confirmation_pending,
            last_rag_source_id=last_rag_source_id,
            last_rag_source_title=last_rag_source_title,
            expected_qualification_field=expected_qualification_field,
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
