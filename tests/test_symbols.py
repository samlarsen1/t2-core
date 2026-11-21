import pytest

from t2core.prices import SymbolError, to_yahoo_symbol


@pytest.mark.parametrize(
    ("t212", "yahoo"),
    [
        ("NVDA_US_EQ", "NVDA"),
        ("BRK_B_US_EQ", "BRK-B"),
        ("RIOl_EQ", "RIO.L"),
        ("NGl_EQ", "NG.L"),
        ("ASMLa_EQ", "ASML.AS"),
        ("SAPd_EQ", "SAP.DE"),
        ("SHOP_CA_EQ", "SHOP.TO"),
        ("VACQ_US_EQ", "RKLB"),
    ],
)
def test_maps_trading212_tickers(t212: str, yahoo: str) -> None:
    assert to_yahoo_symbol(t212) == yahoo


def test_configured_override_wins() -> None:
    assert to_yahoo_symbol("VACQ_US_EQ", {"VACQ_US_EQ": "OTHER"}) == "OTHER"
    assert to_yahoo_symbol("FOOz_EQ", {"FOOz_EQ": "FOO.X"}) == "FOO.X"


@pytest.mark.parametrize("t212", ["FOOz_EQ", "AAPL", "XYZ_JP_EQ"])
def test_unknown_formats_fail_loudly(t212: str) -> None:
    with pytest.raises(SymbolError):
        to_yahoo_symbol(t212)
