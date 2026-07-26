import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://shopkeeper:change_me@localhost:5432/shopkeeper_db",
    )
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    DEFAULT_SHOP_ID: int = int(os.getenv("DEFAULT_SHOP_ID", "1"))
    REMINDER_LOOKAHEAD_DAYS: int = int(os.getenv("REMINDER_LOOKAHEAD_DAYS", "3"))
    REMINDER_CHECK_INTERVAL_HOURS: int = int(os.getenv("REMINDER_CHECK_INTERVAL_HOURS", "24"))


settings = Settings()
