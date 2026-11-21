# T2-CORE

uv project (Python 3.12), `src/t2core`: the shared library for the T2 droids. Version 0.1.0 holds
the price store (`t2core.prices`): one Yahoo Finance source, one Trading212 → Yahoo symbol
mapping, and one SQLite cache.

## System context

Part of the T2 droid system. The hub repo is `../t2-hq`: read its `ARCHITECTURE.md` and
`PLAN.md` (Part 7) before changing what this library offers.
Repos sit side by side in one development directory (`$T2_SRC`) and one apps directory (`$T2_APPS`).

- `../t2-d2`: buys dips; places buy orders on its own timers
- `../t2-k2`: harvests gains from overbought holdings; places sell orders
- `../t2-bb8`: harvests the Trading212 instrument list; metadata only
- `../t2-3po`: advisory council; reviews theses, strategy and configuration; read-only
- `../t2-hq`: hub; plan, architecture, orchestrator and Telegram interface

## Commands

```bash
.venv/bin/pytest                         # tests (tests/)
.venv/bin/pre-commit run --all-files     # detect-secrets, ruff, bandit, semgrep, pip-audit, mypy --strict, pytest
uv sync                                  # install/update deps (uv.lock)
uv run t2-prices update SYMBOL... [--t212] [--since DATE]
```

## Rules

- **A library, not a droid.** No timer, no Trading212 key, no orders, no Telegram. It never
  imports a droid; droids depend on it by git tag.
- **Backwards compatible.** Droids pin a tag, so a breaking change needs a new minor version
  (0.x) and a note in the README.
- **Tests never touch the network.** Use a fake `Fetcher`; `YahooFetcher` is the only code that
  calls yfinance.
- **Adjusted closes by default.** `adj_close` is the dividend-adjusted close; `close` is the
  split-adjusted price on the day. Don't change which one `closes()` returns without updating
  every droid.
- **Never create, read, edit, copy or link `.env` files.** Only write `.env.example` with placeholders.
- **Keep the documents generic.** No personal names, machine names or home-directory paths.
- Git: commit only on `feature/<name>`, `bug/<name>`, `task/<name>` or `hotfix/<name>` branches;
  never directly on `main`.
