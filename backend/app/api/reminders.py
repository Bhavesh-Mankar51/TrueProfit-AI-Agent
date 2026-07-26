from fastapi import APIRouter, Query

from app.reminders import check_due_reminders, get_cached_reminders

router = APIRouter()


@router.get("/reminders")
async def reminders(refresh: bool = Query(False)):
    if refresh or not get_cached_reminders():
        data = await check_due_reminders()
    else:
        data = get_cached_reminders()
    return {"count": len(data), "reminders": data}
