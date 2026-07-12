"""Pydantic request/response schemas: the app's serialization boundary.

Money and percentages arrive here as exact ``Decimal`` from the sim and analysis
layers and leave as JSON numbers rounded for display. The frontend only formats
what these carry; it never recomputes a figure (hard rule #1).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class OrderRequest(BaseModel):
    """A buy or sell, sized by share quantity ("shares") or dollars ("dollars")."""

    symbol: str
    side: Literal["buy", "sell"]
    mode: Literal["shares", "dollars"]
    value: Decimal


class QuoteOut(BaseModel):
    symbol: str
    price: float
    change: float
    percent_change: float
    high: float
    low: float
    open: float
    previous_close: float


class SymbolMatchOut(BaseModel):
    symbol: str
    description: str
    type: str


class CompanyProfileOut(BaseModel):
    symbol: str
    name: str
    exchange: str
    industry: str
    logo: str
    market_cap: float
    blurb: str


class StockOut(BaseModel):
    quote: QuoteOut
    profile: CompanyProfileOut | None


class CandlePointOut(BaseModel):
    date: str
    close: float


class CandlesOut(BaseModel):
    symbol: str
    points: list[CandlePointOut]


class HoldingOut(BaseModel):
    """One holding. Price-derived fields are null when a live quote is unavailable."""

    symbol: str
    quantity: float
    avg_cost: float
    cost_basis: float
    price: float | None
    market_value: float | None
    gain_loss: float | None
    gain_loss_percent: float | None
    weight: float | None


class PortfolioOut(BaseModel):
    cash: float
    starting_balance: float
    total_value: float
    total_cost_basis: float
    total_gain_loss: float
    total_gain_loss_percent: float
    cash_weight: float
    holdings: list[HoldingOut]


class TransactionOut(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    price: float
    total: float
    timestamp: datetime


class OrderResultOut(BaseModel):
    transaction: TransactionOut
    cash: float
