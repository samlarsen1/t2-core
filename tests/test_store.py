from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from t2core.prices import Bar, History, PriceError, PriceStore

TODAY = date(2026, 11, 20)  # a Friday


def weekdays(start: date, end: date) -> list[date]:
    days = []
    day = start
    while day < end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class FakeYahoo:
    """Serves a fixed price series and records every request."""

    def __init__(self, first: date = date(2025, 1, 1), last: date = TODAY) -> None:
        self.closes = {d: 100.0 + i for i, d in enumerate(weekdays(first, last + timedelta(1)))}
        self.adjust = 1.0
        self.dividends: list[tuple[date, float]] = []
        self.calls: list[tuple[date, date]] = []

    def history(self, symbol: str, start: date, end: date) -> History:
        self.calls.append((start, end))
        bars = [
            Bar(d, None, None, None, c, c * self.adjust, 1000.0)
            for d, c in self.closes.items()
            if start <= d < end
        ]
        divs = [(d, a) for d, a in self.dividends if start <= d < end]
        return History(bars=bars, dividends=divs)


@pytest.fixture
def yahoo() -> FakeYahoo:
    return FakeYahoo()


@pytest.fixture
def store(tmp_path: Path, yahoo: FakeYahoo) -> PriceStore:
    return PriceStore(tmp_path / "var" / "prices.db", yahoo)


def test_first_request_downloads_and_caches_completed_bars(
    store: PriceStore, yahoo: FakeYahoo
) -> None:
    start = date(2026, 1, 5)
    bars = store.history("NVDA", start, TODAY)

    assert yahoo.calls == [(start, TODAY + timedelta(1))]
    assert bars[0].day == start
    assert bars[-1].day == TODAY  # today's bar is returned...
    cached = store.cached_bars("NVDA", date.min, date.max)
    assert cached[-1].day == TODAY - timedelta(1)  # ...but not cached
    assert len(cached) == len(bars) - 1


def test_second_request_downloads_only_the_overlap(store: PriceStore, yahoo: FakeYahoo) -> None:
    start = date(2026, 1, 5)
    first = store.history("NVDA", start, TODAY - timedelta(7))
    yahoo.calls.clear()

    second = store.history("NVDA", start, TODAY)

    assert len(yahoo.calls) == 1
    overlap_start, _ = yahoo.calls[0]
    assert overlap_start > start
    assert overlap_start <= first[-1].day
    assert second[-1].day == TODAY
    assert [b.day for b in second] == weekdays(start, TODAY + timedelta(1))


def test_readjusted_prices_trigger_a_full_download(store: PriceStore, yahoo: FakeYahoo) -> None:
    start = date(2026, 1, 5)
    store.history("NG.L", start, TODAY - timedelta(7))
    yahoo.adjust = 0.97  # a dividend re-adjusts every past close
    yahoo.calls.clear()

    bars = store.history("NG.L", start, TODAY)

    assert yahoo.calls[-1] == (start, TODAY + timedelta(1))
    assert all(b.adj_close == pytest.approx(b.close * 0.97) for b in bars)


def test_earlier_start_than_cached_downloads_full_history(
    store: PriceStore, yahoo: FakeYahoo
) -> None:
    store.history("NVDA", date(2026, 6, 1), TODAY)
    yahoo.calls.clear()

    bars = store.history("NVDA", date(2025, 6, 2), TODAY)

    assert yahoo.calls == [(date(2025, 6, 2), TODAY + timedelta(1))]
    assert bars[0].day == date(2025, 6, 2)


def test_later_start_is_served_from_cache(store: PriceStore, yahoo: FakeYahoo) -> None:
    store.history("NVDA", date(2025, 6, 2), TODAY)
    yahoo.calls.clear()

    bars = store.history("NVDA", date(2026, 6, 1), TODAY)

    assert len(yahoo.calls) == 1 and yahoo.calls[0][0] > date(2026, 6, 1)
    assert bars[0].day == date(2026, 6, 1)


def test_closes_are_adjusted_unless_asked(store: PriceStore, yahoo: FakeYahoo) -> None:
    yahoo.adjust = 0.5
    start = date(2026, 11, 2)
    adjusted = store.closes("NVDA", start, TODAY)
    raw = store.closes("NVDA", start, TODAY, adjusted=False)
    assert adjusted == [c * 0.5 for c in raw]


def test_dividends_are_cached(store: PriceStore, yahoo: FakeYahoo) -> None:
    yahoo.dividends = [(date(2026, 6, 4), 0.32), (TODAY, 0.5)]
    store.history("NG.L", date(2026, 1, 5), TODAY)
    assert store.dividends("NG.L", date.min, date.max) == [(date(2026, 6, 4), 0.32)]


def test_symbols_are_kept_apart(store: PriceStore) -> None:
    store.history("NVDA", date(2026, 11, 2), TODAY)
    assert store.cached_bars("AMD", date.min, date.max) == []


def test_no_prices_raises(tmp_path: Path) -> None:
    store = PriceStore(tmp_path / "prices.db", FakeYahoo(first=date(2027, 1, 1)))
    with pytest.raises(PriceError):
        store.history("NEW", date(2026, 1, 5), TODAY)


def test_store_survives_reopening(tmp_path: Path, yahoo: FakeYahoo) -> None:
    path = tmp_path / "prices.db"
    PriceStore(path, yahoo).history("NVDA", date(2026, 11, 2), TODAY)
    assert PriceStore(path, yahoo).cached_bars("NVDA", date.min, date.max)
