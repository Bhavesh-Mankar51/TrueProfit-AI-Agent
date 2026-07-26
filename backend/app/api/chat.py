import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.graph import run_agent

logger = logging.getLogger("shopkeeper.chat")
router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    actions_taken: dict | list | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    logger.info("chat request session=%s message=%r", request.session_id, request.message)
    result = await run_agent(request.session_id, request.message)
    logger.info("chat reply session=%s intent=%s", request.session_id, result.get("intent"))
    return ChatResponse(reply=result["reply"], actions_taken=result.get("tool_ result"))
