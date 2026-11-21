"""Trading212 ticker → Yahoo Finance symbol, in one place for every droid."""

from __future__ import annotations

import re
from collections.abc import Mapping


class SymbolError(ValueError):
    """A Trading212 ticker has no known Yahoo symbol."""


# Lower-case exchange code that Trading212 puts before "_EQ" → Yahoo Finance suffix
EXCHANGE_SUFFIX: dict[str, str] = {
    "l": ".L",  # London
    "d": ".DE",  # Xetra
    "p": ".PA",  # Euronext Paris
    "a": ".AS",  # Euronext Amsterdam
    "e": ".MC",  # Madrid
    "m": ".MI",  # Milan
    "s": ".SW",  # SIX Swiss
    "b": ".BR",  # Euronext Brussels
}
# Country segment ("AAPL_US_EQ") → suffix
COUNTRY_SUFFIX: dict[str, str] = {"US": "", "CA": ".TO"}

# Trading212 tickers whose code isn't the company's symbol, usually because Trading212 kept the
# code of a SPAC or an earlier listing after a merger or rename.
KNOWN_SYMBOLS: dict[str, str] = {
    "VACQ_US_EQ": "RKLB",  # Rocket Lab, listed through the Vector Acquisition SPAC
}

_COUNTRY_RE = re.compile(r"^(?P<symbol>.+)_(?P<country>[A-Z]{2})_EQ$")
_EXCHANGE_RE = re.compile(r"^(?P<symbol>[A-Z0-9.]+?)(?P<exchange>[a-z])_EQ$")


def to_yahoo_symbol(t212_ticker: str, overrides: Mapping[str, str] | None = None) -> str:
    """Map a Trading212 ticker to a Yahoo Finance symbol.

    Args:
        t212_ticker: e.g. ``AAPL_US_EQ``, ``BRK_B_US_EQ``, ``NGl_EQ``, ``ASMLa_EQ``.
        overrides: Trading212 ticker → Yahoo symbol entries from a droid's configuration,
            checked before the built-in ones.

    Returns:
        e.g. ``AAPL``, ``BRK-B``, ``NG.L``, ``ASML.AS``.

    Raises:
        SymbolError: If the format or exchange isn't recognised and there's no override.
    """
    if overrides and t212_ticker in overrides:
        return overrides[t212_ticker]
    if t212_ticker in KNOWN_SYMBOLS:
        return KNOWN_SYMBOLS[t212_ticker]
    match = _COUNTRY_RE.match(t212_ticker)
    if match and match["country"] in COUNTRY_SUFFIX:
        return match["symbol"].replace("_", "-") + COUNTRY_SUFFIX[match["country"]]
    match = _EXCHANGE_RE.match(t212_ticker)
    if match and match["exchange"] in EXCHANGE_SUFFIX:
        return match["symbol"].rstrip(".") + EXCHANGE_SUFFIX[match["exchange"]]
    raise SymbolError(f"no Yahoo symbol for {t212_ticker}; add an override for it")
