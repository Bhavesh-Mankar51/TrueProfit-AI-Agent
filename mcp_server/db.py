import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

_RAW_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://shopkeeper:change_me@localhost:5432/shopkeeper_db",
)
DATABASE_URL = _RAW_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

DEFAULT_SHOP_ID = int(os.getenv("DEFAULT_SHOP_ID", "1"))

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
