from fastapi import APIRouter, HTTPException, Query

from app.agent.mcp_tools import call_tool

router = APIRouter()


@router.get("/reports/summary")
async def reports_summary(
    start_date: str = Query(...),
    end_date: str = Query(...),
    group_by: str = Query("category"),
):
    try:
        result = await call_tool(
            "get_profit_summary", {"start_date": start_date, "end_date": end_date}
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["group_by"] = group_by
    return result
