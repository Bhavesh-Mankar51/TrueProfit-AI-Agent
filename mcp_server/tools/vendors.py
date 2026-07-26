import asyncpg


async def resolve_vendor_id(
    conn: asyncpg.Connection, vendor_name: str | None, shop_id: int
) -> int | None:
    if not vendor_name:
        return None
    row = await conn.fetchrow(
        "SELECT id FROM vendors WHERE shop_id = $1 AND lower(name) = lower($2)",
        shop_id,
        vendor_name,
    )
    if row:
        return row["id"]
    row = await conn.fetchrow(
        "INSERT INTO vendors (shop_id, name) VALUES ($1, $2) RETURNING id",
        shop_id,
        vendor_name,
    )
    return row["id"]
