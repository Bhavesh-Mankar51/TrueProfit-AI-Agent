import os

from dotenv import load_dotenv

load_dotenv()


def to_libpq_dsn(url: str) -> str:
    """SQLAlchemy URLs carry a driver suffix ('+asyncpg') that libpq rejects.

    The LangGraph checkpointer talks to Postgres through psycopg, so it needs a
    plain DSN rather than the SQLAlchemy URL the ORM uses.
    """
    scheme, separator, rest = url.partition("://")
    if not separator:
        return url
    return f"{scheme.split('+', 1)[0]}{separator}{rest}"


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://shopkeeper:change_me@localhost:5432/shopkeeper_db",
    )
    CHECKPOINT_DB_URL: str = os.getenv("CHECKPOINT_DB_URL") or to_libpq_dsn(
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://shopkeeper:change_me@localhost:5432/shopkeeper_db",
        )
    )
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    DEFAULT_SHOP_ID: int = int(os.getenv("DEFAULT_SHOP_ID", "1"))
    REMINDER_LOOKAHEAD_DAYS: int = int(os.getenv("REMINDER_LOOKAHEAD_DAYS", "3"))
    REMINDER_CHECK_INTERVAL_HOURS: int = int(os.getenv("REMINDER_CHECK_INTERVAL_HOURS", "24"))


settings = Settings()
