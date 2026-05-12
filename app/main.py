from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI

from app.di import close_app_state, init_app_state
from app.router.message import router as message_router


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_app_state(app)
    yield
    await close_app_state(app)


app = FastAPI(lifespan=lifespan)
app.include_router(message_router, tags=["Messages"])
