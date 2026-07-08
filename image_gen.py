"""
Слой базы данных на SQLAlchemy (async).

Хранит балансы SCAM (внутренние, off-chain — это не блокчейн-токен) и историю
переводов. Работает и на PostgreSQL (Railway), и на SQLite (локально).

Переменная окружения DATABASE_URL:
  - если задана (Railway обычно подставляет её при добавлении Postgres) — Postgres;
  - если нет — локальный файл SQLite scam.db.
"""

import os
from decimal import Decimal
from datetime import datetime

from sqlalchemy import BigInteger, String, Numeric, DateTime, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Стартовый баланс новичка (чтобы было чем «переводить»)
STARTING_BALANCE = Decimal(os.getenv("STARTING_BALANCE", "1000"))


def _normalize_db_url(url: str | None) -> str:
    if not url:
        return "sqlite+aiosqlite:///scam.db"
    # Railway/Heroku иногда отдают postgres:// — приводим к async-драйверу
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _normalize_db_url(os.getenv("DATABASE_URL"))

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(30, 8), default=STARTING_BALANCE, nullable=False
    )


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    to_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(
    session: AsyncSession, tg_id: int, username: str | None, first_name: str | None
) -> User:
    user = await session.get(User, tg_id)
    if user is None:
        user = User(
            id=tg_id,
            username=username,
            first_name=first_name,
            balance=STARTING_BALANCE,
        )
        session.add(user)
        await session.flush()
    else:
        # держим профиль актуальным
        user.username = username
        user.first_name = first_name
    return user


class TransferError(Exception):
    """Понятная человеку ошибка перевода (недостаточно средств и т.п.)."""


async def do_transfer(
    from_tg: dict, to_tg: dict, amount: Decimal
) -> tuple[Decimal, Decimal]:
    """
    Атомарно переводит amount SCAM от from_tg к to_tg.
    from_tg/to_tg — словари {id, username, first_name}.
    Возвращает (новый баланс отправителя, новый баланс получателя).
    """
    if amount <= 0:
        raise TransferError("Сумма должна быть больше нуля.")
    if from_tg["id"] == to_tg["id"]:
        raise TransferError("Нельзя переводить самому себе.")

    async with Session() as session:
        async with session.begin():
            sender = await get_or_create_user(
                session, from_tg["id"], from_tg["username"], from_tg["first_name"]
            )
            recipient = await get_or_create_user(
                session, to_tg["id"], to_tg["username"], to_tg["first_name"]
            )

            if sender.balance < amount:
                raise TransferError(
                    f"Недостаточно средств. Ваш баланс: {sender.balance} SCAM."
                )

            sender.balance = sender.balance - amount
            recipient.balance = recipient.balance + amount
            session.add(
                Transfer(
                    from_id=sender.id, to_id=recipient.id, amount=amount
                )
            )
            return sender.balance, recipient.balance


async def get_balance(
    tg_id: int, username: str | None, first_name: str | None
) -> Decimal:
    async with Session() as session:
        async with session.begin():
            user = await get_or_create_user(session, tg_id, username, first_name)
            return user.balance


async def get_top(limit: int = 10) -> list[User]:
    async with Session() as session:
        result = await session.execute(
            select(User).order_by(User.balance.desc()).limit(limit)
        )
        return list(result.scalars().all())
