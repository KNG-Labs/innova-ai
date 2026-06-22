from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI

from app.di import close_app_state, init_app_state
from app.router.message_router import router as message_router
from app.router.session_router import router as session_router
from app.router.lead_router import router as lead_router
from app.router.knowledge_router import router as knowledge_router


load_dotenv()


@asynccontextmanager
async def lifespan(current_app: FastAPI) -> AsyncIterator[None]:
    await init_app_state(current_app)
    yield
    await close_app_state(current_app)


app = FastAPI(lifespan=lifespan)
app.include_router(message_router, tags=["Messages"])
app.include_router(session_router)
app.include_router(lead_router)
app.include_router(knowledge_router)
