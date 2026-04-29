from fastapi import FastAPI, Request

from app.gateway.llm_client import StubLLMClient
from app.service.message_service import MessageService


async def init_app_state(app: FastAPI) -> None:
    llm_client = StubLLMClient()
    message_service = MessageService(llm_client)

    app.state.llm_client = llm_client
    app.state.message_service = message_service


async def close_app_state(app: FastAPI) -> None:
    return


def get_message_service(request: Request) -> MessageService:
    return request.app.state.message_service
