from fastapi import APIRouter, HTTPException, Query

from app.agent.mcp_tools import call_tool

router = APIRouter()


@router.get("/dues")
async def dues(type: str = Query(..., pattern="^(vendor|customer)$")):
    try:
        result = await call_tool("list_pending_dues", {"type": type})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"type": type, "dues": result}
