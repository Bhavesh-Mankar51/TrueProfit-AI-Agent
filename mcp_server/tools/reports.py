from mcp_server.db import DEFAULT_SHOP_ID, get_pool
from mcp_server.serialize import jsonable
from mcp_server.validation import clean_date, clean_group_by

_GROUP_EXPR = {
    "category": "category",
    "day": "{date_col}",
    "week": "date_trunc('week', {date_col})::date",
}


async def _grouped_summary(table: str, date_col: str, start_date: str, end_date: str, group_by: str):
    start = clean_date(start_date)
    end = clean_date(end_date)
    group_by = clean_group_by(group_by)

    group_expr = _GROUP_EXPR[group_by].format(date_col=date_col)
    group_label = "category" if group_by == "category" else "period"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {group_expr} AS {group_label}, SUM(amount) AS total, COUNT(*) AS count
            FROM {table}
            WHERE shop_id = $1 AND {date_col} BETWEEN $2 AND $3
            GROUP BY {group_expr}
            ORDER BY {group_expr}
            """,
            DEFAULT_SHOP_ID,
            start,
            end,
        )
        total_row = await conn.fetchrow(
            f"SELECT COALESCE(SUM(amount), 0) AS total FROM {table} WHERE shop_id = $1 AND {date_col} BETWEEN $2 AND $3",
            DEFAULT_SHOP_ID,
            start,
            end,
        )

    breakdown = [
        {group_label: jsonable(r[group_label]), "total": jsonable(r["total"]), "count": r["count"]}
        for r in rows
    ]
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "group_by": group_by,
        "total": jsonable(total_row["total"]),
        "breakdown": breakdown,
    }


async def get_expense_summary(start_date: str, end_date: str, group_by: str = "category") -> dict:
    """Total expenses between start_date and end_date, grouped by category|day|week."""
    return await _grouped_summary("expenses", "expense_date", start_date, end_date, group_by)


async def get_income_summary(start_date: str, end_date: str, group_by: str = "category") -> dict:
    """Total income between start_date and end_date, grouped by category|day|week."""
    return await _grouped_summary("income", "income_date", start_date, end_date, group_by)


async def get_profit_summary(start_date: str, end_date: str) -> dict:
    """Income minus expenses for the period, with per-category breakdowns of each."""
    start = clean_date(start_date)
    end = clean_date(end_date)

    pool = await get_pool()
    async with pool.acquire() as conn:
        income_total = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM income WHERE shop_id = $1 AND income_date BETWEEN $2 AND $3",
            DEFAULT_SHOP_ID,
            start,
            end,
        )
        expense_total = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE shop_id = $1 AND expense_date BETWEEN $2 AND $3",
            DEFAULT_SHOP_ID,
            start,
            end,
        )
        expense_by_category = await conn.fetch(
            """
            SELECT category, SUM(amount) AS total FROM expenses
            WHERE shop_id = $1 AND expense_date BETWEEN $2 AND $3
            GROUP BY category ORDER BY total DESC
            """,
            DEFAULT_SHOP_ID,
            start,
            end,
        )
        income_by_category = await conn.fetch(
            """
            SELECT category, SUM(amount) AS total FROM income
            WHERE shop_id = $1 AND income_date BETWEEN $2 AND $3
            GROUP BY category ORDER BY total DESC
            """,
            DEFAULT_SHOP_ID,
            start,
            end,
        )

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_income": jsonable(income_total),
        "total_expenses": jsonable(expense_total),
        "profit": jsonable(income_total - expense_total),
        "expense_by_category": [
            {"category": r["category"], "total": jsonable(r["total"])} for r in expense_by_category
        ],
        "income_by_category": [
            {"category": r["category"], "total": jsonable(r["total"])} for r in income_by_category
        ],
    }
