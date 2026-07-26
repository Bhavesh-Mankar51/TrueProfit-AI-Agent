from mcp_server.db import DEFAULT_SHOP_ID, get_pool
from mcp_server.serialize import row_to_dict
from mcp_server.tools.vendors import resolve_vendor_id
from mcp_server.validation import (
    clean_amount,
    clean_date,
    clean_name,
    clean_payment_method,
    clean_text,
)


async def log_expense(
    amount: float,
    category: str,
    description: str = "",
    vendor_name: str | None = None,
    payment_method: str = "cash",
    date: str | None = None,
) -> dict:
    """Insert an expense row. Resolves vendor_name to vendor_id if given."""
    amount = clean_amount(amount)
    category = clean_name(category, "category").lower()
    description = clean_text(description)
    payment_method = clean_payment_method(payment_method)
    expense_date = clean_date(date)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            cat_row = await conn.fetchrow(
                "SELECT name FROM categories WHERE lower(name) = $1", category
            )
            if cat_row is None:
                await conn.execute(
                    "INSERT INTO categories (name) VALUES ($1) ON CONFLICT DO NOTHING",
                    category,
                )

            vendor_id = await resolve_vendor_id(conn, vendor_name, DEFAULT_SHOP_ID)

            row = await conn.fetchrow(
                """
                INSERT INTO expenses
                    (shop_id, amount, category, description, vendor_id, payment_method, expense_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, shop_id, amount, category, description, vendor_id,
                          payment_method, expense_date, created_at
                """,
                DEFAULT_SHOP_ID,
                amount,
                category,
                description,
                vendor_id,
                payment_method,
                expense_date,
            )
    return row_to_dict(row)
