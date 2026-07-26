from mcp_server.db import DEFAULT_SHOP_ID, get_pool
from mcp_server.serialize import row_to_dict, rows_to_list
from mcp_server.tools.vendors import resolve_vendor_id
from mcp_server.validation import clean_amount, clean_date, clean_dues_type, clean_name, clean_text


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


async def list_pending_dues(type: str) -> list[dict]:
    """Return unsettled ledger rows. type is 'vendor' (accounts payable — the shop's
    outstanding balance to vendors) or 'customer' (money owed to the shop)."""
    dues_type = clean_dues_type(type)

    pool = await get_pool()
    async with pool.acquire() as conn:
        if dues_type == "vendor":
            rows = await conn.fetch(
                """
                SELECT vl.id, v.name AS vendor_name, vl.amount, vl.due_date, vl.note, vl.created_at
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
                SELECT id, customer_name, amount, credit_date, due_date, note, created_at
                FROM customer_credit
                WHERE status = 'pending' AND type = 'given' AND shop_id = $1
                ORDER BY due_date NULLS LAST, credit_date ASC, created_at ASC
                """,
                DEFAULT_SHOP_ID,
            )
    return rows_to_list(rows)
