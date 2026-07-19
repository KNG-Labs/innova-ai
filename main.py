import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.di import close_app_state, init_app_state
from app.router.message_router import router as message_router
from app.router.session_router import router as session_router
from app.router.lead_router import router as lead_router
from app.router.knowledge_router import router as knowledge_router


load_dotenv()

_STATIC_DIR = Path(__file__).parent / "static"


def _cors_origins() -> list[str]:
    """Origins для виджета. Дефолт '*' — у нас нет cookie-auth (anon_id в body),
    поэтому '*' безопасен и покрывает Origin: null от file://-демо."""
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(current_app: FastAPI) -> AsyncIterator[None]:
    await init_app_state(current_app)
    yield
    await close_app_state(current_app)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(message_router, tags=["Messages"])
app.include_router(session_router)
app.include_router(lead_router)
app.include_router(knowledge_router)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
