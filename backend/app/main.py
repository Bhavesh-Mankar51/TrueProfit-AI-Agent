import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, dues, reminders, reports
from app.config import settings
from app.reminders import check_due_reminders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shopkeeper")

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await check_due_reminders()
    scheduler.add_job(
        check_due_reminders,
        "interval",
        hours=settings.REMINDER_CHECK_INTERVAL_HOURS,
        id="vendor_due_check",
    )
    scheduler.start()
    logger.info("scheduler started: vendor due check every %sh", settings.REMINDER_CHECK_INTERVAL_HOURS)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Shopkeeper Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(reports.router)
app.include_router(dues.router)
app.include_router(reminders.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
