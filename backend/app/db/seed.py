import asyncio

from sqlalchemy import select

from app.db.models import Category, Shop
from app.db.session import async_session_factory

DEFAULT_CATEGORIES = ["inventory", "rent", "electricity", "salary", "transport", "misc"]


async def seed() -> None:
    async with async_session_factory() as session:
        existing_shop = (await session.execute(select(Shop))).scalars().first()
        if not existing_shop:
            session.add(Shop(name="Test General Store", owner_name="Ramesh Shah"))

        existing_categories = {
            c.name for c in (await session.execute(select(Category))).scalars().all()
        }
        for name in DEFAULT_CATEGORIES:
            if name not in existing_categories:
                session.add(Category(name=name))

        await session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
