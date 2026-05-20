from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.db import setup_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_db()
    yield


app = FastAPI(title="Finance Helper", lifespan=lifespan)
app.include_router(chat_router)
