import logging
from datetime import date, timedelta

from sqlalchemy import select

from app.config import settings
from app.db.models import Vendor, VendorLedger
from app.db.session import async_session_factory

logger = logging.getLogger("shopkeeper.reminders")

_cached_reminders: list[dict] = []


async def check_due_reminders(lookahead_days: int | None = None) -> list[dict]:
    lookahead_days = lookahead_days or settings.REMINDER_LOOKAHEAD_DAYS
    cutoff = date.today() + timedelta(days=lookahead_days)

    async with async_session_factory() as session:
        stmt = (
            select(VendorLedger, Vendor.name)
            .join(Vendor, Vendor.id == VendorLedger.vendor_id)
            .where(
                VendorLedger.status == "pending",
                VendorLedger.type == "owed",
                VendorLedger.due_date.is_not(None),
                VendorLedger.due_date <= cutoff,
            )
            .order_by(VendorLedger.due_date.asc())
        )
        rows = (await session.execute(stmt)).all()

    reminders = [
        {
            "vendor_ledger_id": ledger.id,
            "vendor_name": vendor_name,
            "amount": float(ledger.amount - (ledger.paid_amount or 0)),
            "due_date": ledger.due_date.isoformat() if ledger.due_date else None,
            "overdue": ledger.due_date < date.today() if ledger.due_date else False,
            "note": ledger.note,
        }
        for ledger, vendor_name in rows
    ]

    global _cached_reminders
    _cached_reminders = reminders
    logger.info("reminder check found %d due vendor payment(s)", len(reminders))
    return reminders


def get_cached_reminders() -> list[dict]:
    return _cached_reminders
