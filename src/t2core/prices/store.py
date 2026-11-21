"""Daily bars cached in one SQLite file, shared by every droid on a host.

Completed bars are cached; today's bar may still be moving, so it is returned but never stored.
An update downloads only the last few cached days through today. If their adjusted closes no
longer match Yahoo's (Yahoo re-adjusts past prices after a dividend or split), the symbol's
cache is dropped and its full history downloaded again.

The file can be deleted at any time; the next request downloads full histories again.
"""

from __future__ import annotations

import logging
import math
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .models import Bar, Fetcher, History, PriceError

logger = logging.getLogger(__name__)

DB_ENV = "T2_PRICE_DB"
DEFAULT_DB = Path("var/prices.db")

# Incremental updates re-download this many of the latest cached bars and compare them
OVERLAP_BARS = 5
# A cached adjusted close may differ from Yahoo's by this much before the cache is stale
CLOSE_RTOL = 1e-3

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol    TEXT NOT NULL,
    day       TEXT NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL NOT NULL,
    adj_close REAL NOT NULL,
    volume    REAL,
    PRIMARY KEY (symbol, day)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS dividends (
    symbol TEXT NOT NULL,
    day    TEXT NOT NULL,
    amount REAL NOT NULL,
    PRIMARY KEY (symbol, day)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS splits (
    symbol TEXT NOT NULL,
    day    TEXT NOT NULL,
    ratio  REAL NOT NULL,
    PRIMARY KEY (symbol, day)
) WITHOUT ROWID;
-- history_start: the earliest day the cache has asked Yahoo for. Bars may start later if the
-- symbol was listed later.
CREATE TABLE IF NOT EXISTS symbols (
    symbol        TEXT PRIMARY KEY,
    history_start TEXT NOT NULL,
    updated_at    TEXT NOT NULL
) WITHOUT ROWID;
"""


def default_db_path() -> Path:
    """``$T2_PRICE_DB`` if set, else ``var/prices.db`` under the current directory."""
    configured = os.environ.get(DB_ENV)
    return Path(configured) if configured else DEFAULT_DB


class PriceStore:
    """Daily bars from a fetcher, cached in SQLite.

    Args:
        path: The SQLite file; created, with its folder, on first use.
        fetcher: Where bars come from; Yahoo Finance by default.
    """

    def __init__(self, path: Path, fetcher: Fetcher | None = None) -> None:
        if fetcher is None:
            from .yahoo import YahooFetcher

            fetcher = YahooFetcher()
        self.path = path
        self._fetcher = fetcher

    # ------------------------------------------------------------------ connection

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """A connection per call, so threads and processes can share the file safely."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.executescript(SCHEMA)
            with conn:  # one transaction
                yield conn

    # ------------------------------------------------------------------ reading

    def cached_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        """Cached bars dated ``start`` ≤ day < ``end``, oldest first. Never fetches."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT day, open, high, low, close, adj_close, volume FROM bars"
                " WHERE symbol = ? AND day >= ? AND day < ? ORDER BY day",
                (symbol, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            Bar(date.fromisoformat(day), o, h, low, c, a, v) for day, o, h, low, c, a, v in rows
        ]

    def dividends(self, symbol: str, start: date, end: date) -> list[tuple[date, float]]:
        """Cached dividends dated ``start`` ≤ day < ``end``, oldest first. Never fetches."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT day, amount FROM dividends"
                " WHERE symbol = ? AND day >= ? AND day < ? ORDER BY day",
                (symbol, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [(date.fromisoformat(day), amount) for day, amount in rows]

    def history(self, symbol: str, start: date, today: date | None = None) -> list[Bar]:
        """Bars from ``start`` through today, updating the cache first.

        Today's bar, if Yahoo has one, is included but not cached.

        Raises:
            PriceError: If the prices can't be fetched, or Yahoo has none for the window.
        """
        today = today or date.today()
        live = self.update(symbol, start, today)
        bars = self.cached_bars(symbol, start, today)
        if live is not None:
            bars.append(live)
        if not bars:
            raise PriceError(f"no prices for {symbol} since {start}")
        return bars

    def closes(
        self, symbol: str, start: date, today: date | None = None, *, adjusted: bool = True
    ) -> list[float]:
        """Closes from ``start`` through today, oldest first; adjusted for dividends by default."""
        return [b.adj_close if adjusted else b.close for b in self.history(symbol, start, today)]

    # ------------------------------------------------------------------ updating

    def update(self, symbol: str, start: date, today: date | None = None) -> Bar | None:
        """Make the cache cover ``start`` up to yesterday, downloading as little as possible.

        Returns:
            Today's bar if Yahoo has one yet (not cached), else ``None``.

        Raises:
            PriceError: If the download fails.
        """
        today = today or date.today()
        end = today + timedelta(days=1)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT history_start FROM symbols WHERE symbol = ?", (symbol,)
            ).fetchone()
            tail = conn.execute(
                "SELECT day, adj_close FROM bars WHERE symbol = ? ORDER BY day DESC LIMIT ?",
                (symbol, OVERLAP_BARS),
            ).fetchall()
        covered = row is not None and date.fromisoformat(row[0]) <= start and bool(tail)

        if covered:
            cached = {date.fromisoformat(day): adj for day, adj in tail}
            fresh = self._fetcher.history(symbol, min(cached), end)
            if _overlap_matches(cached, fresh):
                self._save(symbol, fresh, today, history_start=None)
                return _live_bar(fresh, today)
            logger.info("price cache stale for %s; downloading full history", symbol)

        full = self._fetcher.history(symbol, start, end)
        if not full.bars:
            raise PriceError(f"Yahoo returned no prices for {symbol} since {start}")
        self._save(symbol, full, today, history_start=start, replace=True)
        return _live_bar(full, today)

    def _save(
        self,
        symbol: str,
        history: History,
        today: date,
        *,
        history_start: date | None,
        replace: bool = False,
    ) -> None:
        completed = [b for b in history.bars if b.day < today]
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            if replace:
                for table in ("bars", "dividends", "splits"):
                    conn.execute(f"DELETE FROM {table} WHERE symbol = ?", (symbol,))  # nosec B608
            conn.executemany(
                "INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (symbol, b.day.isoformat(), b.open, b.high, b.low, b.close, b.adj_close,
                     b.volume)
                    for b in completed
                ],
            )
            conn.executemany(
                "INSERT OR REPLACE INTO dividends VALUES (?, ?, ?)",
                [(symbol, d.isoformat(), amount) for d, amount in history.dividends if d < today],
            )
            conn.executemany(
                "INSERT OR REPLACE INTO splits VALUES (?, ?, ?)",
                [(symbol, d.isoformat(), ratio) for d, ratio in history.splits if d < today],
            )
            if history_start is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO symbols VALUES (?, ?, ?)",
                    (symbol, history_start.isoformat(), now),
                )
            else:
                conn.execute("UPDATE symbols SET updated_at = ? WHERE symbol = ?", (now, symbol))


def _overlap_matches(cached: dict[date, float], fresh: History) -> bool:
    """True if every cached day that Yahoo returned again has (nearly) the same adjusted close."""
    returned = {b.day: b.adj_close for b in fresh.bars}
    common = cached.keys() & returned.keys()
    if not common:
        return False
    return all(math.isclose(cached[d], returned[d], rel_tol=CLOSE_RTOL) for d in common)


def _live_bar(history: History, today: date) -> Bar | None:
    last = history.bars[-1] if history.bars else None
    return last if last is not None and last.day >= today else None
