"""Daily history from Yahoo Finance, through yfinance."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from .models import Bar, History, PriceError


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def history_from_frame(frame: Any) -> History:
    """Convert a yfinance ``Ticker.history(auto_adjust=False, actions=True)`` frame."""
    if frame is None or frame.empty:
        return History()
    bars: list[Bar] = []
    dividends: list[tuple[date, float]] = []
    splits: list[tuple[date, float]] = []
    for ts, row in frame.iterrows():
        day = ts.date()
        close = _number(row.get("Close"))
        if close is not None and close > 0:
            adj_close = _number(row.get("Adj Close"))
            bars.append(
                Bar(
                    day=day,
                    open=_number(row.get("Open")),
                    high=_number(row.get("High")),
                    low=_number(row.get("Low")),
                    close=close,
                    adj_close=adj_close if adj_close is not None and adj_close > 0 else close,
                    volume=_number(row.get("Volume")),
                )
            )
        dividend = _number(row.get("Dividends"))
        if dividend:
            dividends.append((day, dividend))
        split = _number(row.get("Stock Splits"))
        if split:
            splits.append((day, split))
    return History(bars=bars, dividends=dividends, splits=splits)


class YahooFetcher:
    """Fetches daily bars, dividends and splits from Yahoo Finance."""

    def history(self, symbol: str, start: date, end: date) -> History:
        """Return bars dated ``start`` ≤ day < ``end``.

        Raises:
            PriceError: If the request fails.
        """
        import yfinance as yf  # deferred: slow import, and tests never need it

        try:
            frame = yf.Ticker(symbol).history(
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=True,
            )
        except Exception as exc:  # yfinance raises a wide, undocumented set of errors
            raise PriceError(f"Yahoo request for {symbol} failed ({type(exc).__name__})") from exc
        return history_from_frame(frame)
