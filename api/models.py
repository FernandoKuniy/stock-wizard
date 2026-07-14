"""SQLAlchemy ORM models: the persistent shape of the simulation.

Money is stored as ``Numeric`` (Python ``Decimal``), never float, because these
are real balances in the sim and must stay exact.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base all models inherit from."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The Supabase Auth user this row belongs to (the token's ``sub`` claim). This is
    # the real identity; ``email`` is just a copy for display, and Supabase owns its
    # uniqueness. Nullable because rows seeded before auth existed have no Supabase
    # user, and nothing can sign in as them.
    auth_id: Mapped[UUID | None] = mapped_column(Uuid(), unique=True, index=True, default=None)
    email: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    accounts: Mapped[list[Account]] = relationship(back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    starting_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="accounts")
    holdings: Mapped[list[Holding]] = relationship(back_populates="account")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="account")


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4))

    account: Mapped[Account] = relationship(back_populates="holdings")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("side in ('buy', 'sell')", name="ck_transactions_side"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="transactions")
