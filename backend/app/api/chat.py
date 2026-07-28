import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.agent.graph import get_history, run_agent

logger = logging.getLogger("shopkeeper.chat")
router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    actions_taken: dict | list | None = None


class HistoryMessage(BaseModel):
    role: str
    text: str


class HistoryResponse(BaseModel):
    messages: list[HistoryMessage]


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    logger.info("chat request session=%s message=%r", request.session_id, request.message)
    result = await run_agent(request.session_id, request.message)
    logger.info("chat reply session=%s intent=%s", request.session_id, result.get("intent"))
    return ChatResponse(reply=result["reply"], actions_taken=result.get("tool_result"))


@router.get("/chat/history", response_model=HistoryResponse)
async def chat_history(session_id: str = Query(...)) -> HistoryResponse:
    messages = await get_history(session_id)
    logger.info("chat history session=%s messages=%d", session_id, len(messages))
    return HistoryResponse(messages=[HistoryMessage(**m) for m in messages])
