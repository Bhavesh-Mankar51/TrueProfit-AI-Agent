from decimal import Decimal

from mcp_server.db import DEFAULT_SHOP_ID, get_pool
from mcp_server.serialize import row_to_dict
from mcp_server.validation import (
    clean_amount,
    clean_date,
    clean_income_category,
    clean_payment_method,
    clean_text,
)


async def log_income(
    amount: float,
    category: str,
    item_description: str = "",
    customer_name: str | None = None,
    payment_method: str = "cash",
    date: str | None = None,
) -> dict:
    """Insert an income row (cash_sale | online_payment). Use
    log_credit_repayment instead when the payment settles existing customer
    credit."""
    amount = clean_amount(amount)
    category = clean_income_category(category)
    if category == "credit_repayment":
        raise ValueError("use log_credit_repayment for credit repayments, not log_income")
    item_description = clean_text(item_description)
    customer_name = clean_text(customer_name, max_len=200)
    payment_method = clean_payment_method(payment_method)
    income_date = clean_date(date)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO income
                (shop_id, amount, category, item_description, customer_name, payment_method, income_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, shop_id, amount, category, item_description, customer_name,
                      payment_method, income_date, created_at
            """,
            DEFAULT_SHOP_ID,
            amount,
            category,
            item_description,
            customer_name,
            payment_method,
            income_date,
        )
    return row_to_dict(row)


async def log_credit_repayment(customer_name: str, amount: float, date: str | None = None) -> dict:
    """Log a customer repaying credit they owed. Writes an income row
    (category=credit_repayment) and marks matching customer_credit rows as
    settled (oldest first), in one transaction."""
    amount = clean_amount(amount)
    customer_name = customer_name.strip() if customer_name else ""
    if not customer_name:
        raise ValueError("customer_name is required")
    income_date = clean_date(date)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            income_row = await conn.fetchrow(
                """
                INSERT INTO income
                    (shop_id, amount, category, customer_name, income_date)
                VALUES ($1, $2, 'credit_repayment', $3, $4)
                RETURNING id, shop_id, amount, category, customer_name, income_date, created_at
                """,
                DEFAULT_SHOP_ID,
                amount,
                customer_name,
                income_date,
            )

            pending_rows = await conn.fetch(
                """
                SELECT id, amount FROM customer_credit
                WHERE shop_id = $1 AND lower(customer_name) = lower($2)
                  AND type = 'given' AND status = 'pending'
                ORDER BY credit_date ASC, id ASC
                FOR UPDATE
                """,
                DEFAULT_SHOP_ID,
                customer_name,
            )

            remaining = amount
            settled_ids: list[int] = []
            for row in pending_rows:
                if remaining <= 0:
                    break
                settled_ids.append(row["id"])
                remaining -= row["amount"]

            if settled_ids:
                await conn.execute(
                    "UPDATE customer_credit SET status = 'settled' WHERE id = ANY($1::int[])",
                    settled_ids,
                )

    result = row_to_dict(income_row)
    result["settled_customer_credit_ids"] = settled_ids
    result["unmatched_amount"] = float(max(remaining, Decimal("0")))
    return result
