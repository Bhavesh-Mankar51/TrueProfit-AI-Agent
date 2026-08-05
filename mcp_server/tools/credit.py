from mcp_server.db import DEFAULT_SHOP_ID, get_pool
from mcp_server.serialize import row_to_dict, rows_to_list
from mcp_server.tools.vendors import resolve_vendor_id
from mcp_server.validation import (
    clean_amount,
    clean_date,
    clean_dues_type,
    clean_name,
    clean_payment_method,
    clean_text,
)

VENDOR_PAYMENT_CATEGORY = "vendor_payment"


async def add_vendor_credit(
    vendor_name: str, amount: float, due_date: str | None = None, note: str | None = None
) -> dict:
    """Record an accounts payable entry for a vendor. Resolves/creates the vendor by name."""
    vendor_name = clean_name(vendor_name, "vendor_name")
    amount = clean_amount(amount)
    due_date_cleaned = clean_date(due_date) if due_date else None
    note = clean_text(note)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            vendor_id = await resolve_vendor_id(conn, vendor_name, DEFAULT_SHOP_ID)
            row = await conn.fetchrow(
                """
                INSERT INTO vendor_ledger (vendor_id, amount, type, due_date, note)
                VALUES ($1, $2, 'owed', $3, $4)
                RETURNING id, vendor_id, amount, type, due_date, status, note, created_at
                """,
                vendor_id,
                amount,
                due_date_cleaned,
                note,
            )
    result = row_to_dict(row)
    result["vendor_name"] = vendor_name
    return result


async def add_customer_credit(
    customer_name: str,
    amount: float,
    due_date: str | None = None,
    note: str | None = None,
    date: str | None = None,
) -> dict:
    """Record goods/money given to a customer on credit (udhaar)."""
    customer_name = clean_name(customer_name, "customer_name")
    amount = clean_amount(amount)
    credit_date = clean_date(date)
    due_date_cleaned = clean_date(due_date) if due_date else None
    note = clean_text(note)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO customer_credit (shop_id, customer_name, amount, type, note, credit_date, due_date)
            VALUES ($1, $2, $3, 'given', $4, $5, $6)
            RETURNING id, shop_id, customer_name, amount, type, status, note, credit_date, due_date, created_at
            """,
            DEFAULT_SHOP_ID,
            customer_name,
            amount,
            note,
            credit_date,
            due_date_cleaned,
        )
    return row_to_dict(row)


async def log_vendor_payment(
    vendor_name: str,
    amount: float,
    payment_method: str = "cash",
    date: str | None = None,
    note: str | None = None,
) -> dict:
    """Log the shop paying a vendor money it owed. Writes an expense row
    (category=vendor_payment) and applies the money to that vendor's pending
    vendor_ledger rows oldest first, in one transaction. Part payments reduce a
    bill's outstanding balance; a bill is marked settled once fully paid. Use
    log_expense instead for a fresh purchase never recorded as a credit due."""
    vendor_name = clean_name(vendor_name, "vendor_name")
    amount = clean_amount(amount)
    payment_method = clean_payment_method(payment_method)
    payment_date = clean_date(date)
    note = clean_text(note)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            vendor_id = await resolve_vendor_id(conn, vendor_name, DEFAULT_SHOP_ID)

            pending_rows = await conn.fetch(
                """
                SELECT id, amount, paid_amount FROM vendor_ledger
                WHERE vendor_id = $1 AND type = 'owed' AND status = 'pending'
                ORDER BY due_date NULLS LAST, created_at ASC, id ASC
                FOR UPDATE
                """,
                vendor_id,
            )

            remaining = amount
            settled_ids: list[int] = []
            applied: list[dict] = []
            for row in pending_rows:
                if remaining <= 0:
                    break
                outstanding = row["amount"] - row["paid_amount"]
                if outstanding <= 0:
                    continue

                applied_now = min(outstanding, remaining)
                remaining -= applied_now
                new_paid = row["paid_amount"] + applied_now
                fully_paid = new_paid >= row["amount"]

                await conn.execute(
                    "UPDATE vendor_ledger SET paid_amount = $2, status = $3 WHERE id = $1",
                    row["id"],
                    new_paid,
                    "settled" if fully_paid else "pending",
                )
                if fully_paid:
                    settled_ids.append(row["id"])
                applied.append(
                    {
                        "vendor_ledger_id": row["id"],
                        "applied_amount": float(applied_now),
                        "remaining_on_bill": float(row["amount"] - new_paid),
                    }
                )

            await conn.execute(
                "INSERT INTO categories (name) VALUES ($1) ON CONFLICT DO NOTHING",
                VENDOR_PAYMENT_CATEGORY,
            )

            expense_row = await conn.fetchrow(
                """
                INSERT INTO expenses
                    (shop_id, amount, category, description, vendor_id, payment_method, expense_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, shop_id, amount, category, description, vendor_id,
                          payment_method, expense_date, created_at
                """,
                DEFAULT_SHOP_ID,
                amount,
                VENDOR_PAYMENT_CATEGORY,
                note or f"Payment to {vendor_name}",
                vendor_id,
                payment_method,
                payment_date,
            )

    result = row_to_dict(expense_row)
    result["vendor_name"] = vendor_name
    result["settled_vendor_ledger_ids"] = settled_ids
    result["applied_to"] = applied
    result["unapplied_amount"] = float(remaining)
    return result


async def list_pending_dues(type: str) -> list[dict]:
    """Return unsettled ledger rows. type is 'vendor' (accounts payable — the shop's
    outstanding balance to vendors) or 'customer' (money owed to the shop)."""
    dues_type = clean_dues_type(type)

    pool = await get_pool()
    async with pool.acquire() as conn:
        if dues_type == "vendor":
            rows = await conn.fetch(
                """
                SELECT vl.id, v.name AS vendor_name,
                       vl.amount - vl.paid_amount AS amount,
                       vl.amount AS original_amount, vl.paid_amount,
                       vl.due_date, vl.note, vl.created_at
                FROM vendor_ledger vl
                JOIN vendors v ON v.id = vl.vendor_id
                WHERE vl.status = 'pending' AND vl.type = 'owed' AND v.shop_id = $1
                ORDER BY vl.due_date NULLS LAST, vl.created_at ASC
                """,
                DEFAULT_SHOP_ID,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, customer_name,
                       amount - paid_amount AS amount,
                       amount AS original_amount, paid_amount,
                       credit_date, due_date, note, created_at
                FROM customer_credit
                WHERE status = 'pending' AND type = 'given' AND shop_id = $1
                ORDER BY due_date NULLS LAST, credit_date ASC, created_at ASC
                """,
                DEFAULT_SHOP_ID,
            )
    return rows_to_list(rows)
