from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent import process_user_message
from app.tools import CURRENT_SESSION

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any]
    result: Any


class ChatResponse(BaseModel):
    reply: str
    session: int
    tool_calls: list[ToolCallRecord]


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    result = process_user_message(body.message, CURRENT_SESSION)
    return ChatResponse(
        reply=result["reply"],
        session=result["session"],
        tool_calls=[ToolCallRecord(**tc) for tc in result["tool_calls"]],
    )
