from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.di import close_app_state, init_app_state
from app.router.message_router import router as message_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_app_state(app)
    yield
    await close_app_state(app)


app = FastAPI(lifespan=lifespan)
app.include_router(message_router)
