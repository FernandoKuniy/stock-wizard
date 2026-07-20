"""SQLAlchemy ORM models: the persistent shape of the simulation.

Money is stored as ``Numeric`` (Python ``Decimal``), never float, because these
are real balances in the sim and must stay exact.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
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
    watchlist_items: Mapped[list[WatchlistItem]] = relationship(back_populates="account")
    orders: Mapped[list[Order]] = relationship(back_populates="account")


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


class Order(Base):
    """A limit order resting until the market reaches the price the user asked for.

    Nothing is set aside when an order is placed: cash moves only at fill. If the account
    can't cover it by the time the price crosses, the order is cancelled with a reason
    rather than partly filled. Orders are good until cancelled, and they're checked when
    the user loads their portfolio or their orders, since this app deliberately runs no
    background job (see services/sim/orders.py).
    """

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("side in ('buy', 'sell')", name="ck_orders_side"),
        CheckConstraint("status in ('open', 'filled', 'cancelled')", name="ck_orders_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    limit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # The trade this order became, once it filled.
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), default=None)
    # Why we cancelled it on the user's behalf, so the UI can explain rather than just say no.
    cancel_reason: Mapped[str | None] = mapped_column(String(200), default=None)

    account: Mapped[Account] = relationship(back_populates="orders")
    transaction: Mapped[Transaction | None] = relationship()


class WatchlistItem(Base):
    """A symbol an account is tracking, without owning it. No money is involved: this is
    just a list of tickers the user wants to keep an eye on, scoped to their account like
    everything else. One row per (account, symbol); adding a symbol already present is a
    no-op."""

    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_watchlist_account_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="watchlist_items")
