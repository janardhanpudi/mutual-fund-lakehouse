import pandas as pd
import pytest

from mf_lakehouse.extract.index_prices import IndexPriceError, to_long


def fake_download(nifty_close=(100.0, 101.0), sensex_close=(300.0, 301.0)):
    """A small table shaped like yf.download(..., group_by='ticker')."""
    dates = pd.to_datetime(["2026-10-29", "2026-10-30"]).rename("Date")
    cols = pd.MultiIndex.from_product([["^NSEI", "^BSESN"], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    raw = pd.DataFrame(index=dates, columns=cols, dtype=float)
    for ticker, closes in [("^NSEI", nifty_close), ("^BSESN", sensex_close)]:
        for field in ["Open", "High", "Low", "Close", "Adj Close"]:
            raw[(ticker, field)] = closes
        raw[(ticker, "Volume")] = 1000
    return raw


def test_long_shape():
    df = to_long(fake_download())
    assert list(df.columns) == ["ticker", "price_date", "open", "high", "low", "close"]
    assert len(df) == 4
    assert df.loc[df["ticker"] == "^BSESN", "close"].tolist() == [300.0, 301.0]
    assert df["price_date"].tolist()[:2] == ["2026-10-29", "2026-10-30"]


def test_missing_close_row_is_dropped():
    # Like 2025-02-01: Nifty traded, Sensex has no close in Yahoo's data
    df = to_long(fake_download(sensex_close=(300.0, None)))
    assert len(df[df["ticker"] == "^BSESN"]) == 1


def test_ticker_with_no_data_raises():
    with pytest.raises(IndexPriceError, match="No closing prices"):
        to_long(fake_download(sensex_close=(None, None)))


def test_non_positive_close_raises():
    with pytest.raises(IndexPriceError, match="Non-positive"):
        to_long(fake_download(nifty_close=(100.0, 0.0)))