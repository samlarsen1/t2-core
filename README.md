# t2-core

Shared library for the T2 droids. Version 0.1.0 holds one thing: **the price store**, one daily
price source and cache that every droid, the trade ledger and the backtester can share.

## Part of the T2 system

This repo is one of the T2 repos, coordinated from the `t2-hq` repo, which holds the system
architecture (`ARCHITECTURE.md`) and plan (`PLAN.md`, Part 7). All the T2 repos live under the
same GitHub owner as this one.

| Repo | Role |
|---|---|
| `t2-d2` | buys dips; places buy orders on its own timers |
| `t2-k2` | harvests gains from overbought holdings; places sell orders |
| `t2-bb8` | harvests the Trading212 instrument list; metadata only |
| `t2-3po` | advisory council; reviews theses, strategy and configuration; read-only |
| `t2-hq` | hub: plan, architecture, and the orchestrator and Telegram interface |
| **t2-core** (this repo) | shared library: the price store |

t2-core is a library, not a droid: it has no timer and no Trading212 key. No droid depends on it
yet; each moves over in its own pull request.

## The price store

```python
from datetime import date
from pathlib import Path

from t2core.prices import PriceStore, to_yahoo_symbol

store = PriceStore(Path("var/prices.db"))
symbol = to_yahoo_symbol("NGl_EQ")                  # "NG.L"
closes = store.closes(symbol, date(2025, 11, 1))    # dividend-adjusted, oldest first
bars = store.history(symbol, date(2025, 11, 1))     # Bar: day, open, high, low, close, adj_close, volume
divs = store.dividends(symbol, date(2025, 1, 1), date.today())
```

Decisions made once, here, for every droid:

- **Two closes per bar.** `close` is adjusted for splits only: what the price actually was.
  `adj_close` is also adjusted for dividends, so an ex-dividend drop doesn't look like a dip.
  `closes()` returns adjusted closes unless you pass `adjusted=False`. Use adjusted closes for
  returns and signals, which is what `t2-d2`, `t2-k2` and `t2-3po` already do.
- **Dividends and splits are stored** alongside the bars, for ex-dividend and earnings work.
- **Prices are in Yahoo's quote currency**, which is pence for the LSE.
- **One symbol mapping.** `to_yahoo_symbol` turns a Trading212 ticker into a Yahoo symbol
  (`AAPL_US_EQ` → `AAPL`, `BRK_B_US_EQ` → `BRK-B`, `NGl_EQ` → `NG.L`, `ASMLa_EQ` → `ASML.AS`).
  Tickers that Trading212 kept from an earlier listing are listed in `KNOWN_SYMBOLS`
  (`VACQ_US_EQ` → `RKLB`), and a droid's own configuration can override any of them. Unknown
  formats raise `SymbolError` rather than guessing.

### Caching

- One SQLite file, `$T2_PRICE_DB` or `var/prices.db`. Point every droid on a host at the same
  file to share it; SQLite's WAL mode lets them read and write at the same time.
- Completed bars are cached. Today's bar may still be moving, so it is returned but never stored.
- A request that the cache already covers downloads only the last five cached days through
  today. If their adjusted closes no longer match Yahoo's (Yahoo re-adjusts history after a
  dividend or split), that symbol's cache is dropped and its full history downloaded again.
- A request that starts earlier than anything cached downloads the full window.
- The file is always safe to delete; the next request downloads full histories again.

### Command line

```bash
uv run t2-prices update NVDA NG.L --since 2016-01-01        # Yahoo symbols
uv run t2-prices update --t212 VACQ_US_EQ NGl_EQ --since 2016-01-01
uv run t2-prices show NG.L --days 10                         # cached bars only, no download
```

Exit codes follow the droid contract: 0 ok, 1 failed, 2 usage error.

## Development

Requires Python 3.12 and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
.venv/bin/pre-commit install --install-hooks
.venv/bin/pre-commit run --all-files   # detect-secrets, ruff, bandit, semgrep, pip-audit, mypy --strict, pytest
```

## License

MIT
