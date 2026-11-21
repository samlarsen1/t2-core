from datetime import date

import pandas as pd

from t2core.prices.yahoo import history_from_frame


def test_converts_a_yfinance_frame() -> None:
    frame = pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0],
            "High": [10.5, 11.5, 12.5],
            "Low": [9.5, 10.5, float("nan")],
            "Close": [10.0, 11.0, float("nan")],
            "Adj Close": [9.8, 10.9, float("nan")],
            "Volume": [100, 200, 0],
            "Dividends": [0.0, 0.2, 0.0],
            "Stock Splits": [0.0, 0.0, 2.0],
        },
        index=pd.DatetimeIndex(["2026-11-18", "2026-11-19", "2026-11-20"], tz="Europe/London"),
    )

    history = history_from_frame(frame)

    assert [b.day for b in history.bars] == [date(2026, 11, 18), date(2026, 11, 19)]
    assert history.bars[0].adj_close == 9.8
    assert history.dividends == [(date(2026, 11, 19), 0.2)]
    assert history.splits == [(date(2026, 11, 20), 2.0)]


def test_missing_adjusted_close_falls_back_to_close() -> None:
    frame = pd.DataFrame({"Close": [10.0]}, index=pd.DatetimeIndex(["2026-11-18"]))
    assert history_from_frame(frame).bars[0].adj_close == 10.0


def test_empty_frame() -> None:
    assert history_from_frame(pd.DataFrame()).bars == []
