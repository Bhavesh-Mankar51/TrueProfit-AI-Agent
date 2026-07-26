import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg

import mcp_server.db as db_module
from mcp_server.db import DATABASE_URL

_TABLES_IN_DELETE_ORDER = ["expenses", "income", "vendor_ledger", "customer_credit", "vendors"]


@pytest.fixture
async def db_pool():
    db_module._pool = None
    try:
        pool = await db_module.get_pool()
        async with pool.acquire() as conn:
            for table in _TABLES_IN_DELETE_ORDER:
                await conn.execute(f"DELETE FROM {table}")
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable/usable at {DATABASE_URL}: {exc}")
        return
    yield pool
    await db_module.close_pool()
