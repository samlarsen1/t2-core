"""``t2-prices``: fill and inspect the shared price store.

    t2-prices update NVDA NG.L --since 2016-01-01
    t2-prices update --t212 VACQ_US_EQ NGl_EQ --since 2016-01-01
    t2-prices show NVDA --days 10
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from .models import PriceError
from .store import PriceStore, default_db_path
from .symbols import SymbolError, to_yahoo_symbol


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="t2-prices", description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, help="SQLite file (default: $T2_PRICE_DB or "
                        "var/prices.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    update = sub.add_parser("update", help="download history into the store")
    update.add_argument("symbols", nargs="+", help="Yahoo symbols, or Trading212 tickers with "
                        "--t212")
    update.add_argument("--t212", action="store_true", help="symbols are Trading212 tickers")
    update.add_argument("--since", type=date.fromisoformat,
                        default=date.today() - timedelta(days=400),
                        help="first day to cover (default: about 13 months ago)")

    show = sub.add_parser("show", help="print the latest cached bars (no download)")
    show.add_argument("symbol")
    show.add_argument("--days", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command; exit codes follow the droid contract (0 ok, 1 failed, 2 usage)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parser().parse_args(argv)
    store = PriceStore(args.db or default_db_path())

    if args.command == "show":
        bars = store.cached_bars(args.symbol, date.min, date.max)[-args.days:]
        if not bars:
            print(f"nothing cached for {args.symbol}")
            return 1
        print(f"{'day':<12}{'close':>12}{'adj_close':>12}")
        for bar in bars:
            print(f"{bar.day.isoformat():<12}{bar.close:>12.4f}{bar.adj_close:>12.4f}")
        return 0

    failed = 0
    for given in args.symbols:
        try:
            symbol = to_yahoo_symbol(given) if args.t212 else given
        except SymbolError as exc:
            print(exc, file=sys.stderr)
            return 2
        try:
            bars = store.history(symbol, args.since)
        except PriceError as exc:
            print(f"{symbol}: {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{symbol}: {len(bars)} bars, {bars[0].day} to {bars[-1].day}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
