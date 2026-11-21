"""Daily bars and the source they're fetched from."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


class PriceError(Exception):
    """Prices couldn't be fetched or are unusable."""


@dataclass(frozen=True)
class Bar:
    """One day's prices for one symbol, in the currency Yahoo quotes it in (pence for LSE).

    ``close`` is adjusted for splits only; ``adj_close`` is also adjusted for dividends, so an
    ex-dividend drop doesn't show as a fall. Use ``adj_close`` for returns and dip signals, and
    ``close`` for what the price actually was on the day.
    """

    day: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float
    volume: float | None


@dataclass(frozen=True)
class History:
    """Bars plus the dividends and splits in the same window, oldest first."""

    bars: list[Bar] = field(default_factory=list)
    dividends: list[tuple[date, float]] = field(default_factory=list)
    splits: list[tuple[date, float]] = field(default_factory=list)


class Fetcher(Protocol):
    """A source of daily history, such as Yahoo Finance."""

    def history(self, symbol: str, start: date, end: date) -> History:
        """Return bars dated ``start`` ≤ day < ``end``; an empty history if there are none.

        Raises:
            PriceError: If the request fails.
        """
        ...
