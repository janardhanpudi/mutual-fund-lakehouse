"""Benchmark index prices (Nifty 50, Sensex) from yfinance."""

from __future__ import annotations

import warnings

# yfinance itself still uses pandas' deprecated inplace=; not our code, so hide only those
warnings.filterwarnings("ignore", message="The inplace keyword", module="yfinance")

import argparse
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from mf_lakehouse.common.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

TICKERS = ("^NSEI", "^BSESN")  # Nifty 50, Sensex
PRICE_COLUMNS = {"Open": "open", "High": "high", "Low": "low", "Close": "close"}
DEFAULT_OUT = PROJECT_ROOT / "data" / "landing" / "index_prices"
LOOKBACK_DAYS = 7


class IndexPriceError(ValueError):
    """yfinance returned data this extractor cannot trust."""


def to_long(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn yfinance's wide table (one column group per ticker) into one row per ticker per date."""
    parts = []
    for ticker in TICKERS:
        if ticker not in raw.columns.get_level_values(0):
            raise IndexPriceError(f"No data returned for {ticker}")
        t = raw[ticker][list(PRICE_COLUMNS)].rename(columns=PRICE_COLUMNS)
        t = t.dropna(subset=["close"])
        if t.empty:
            raise IndexPriceError(f"No closing prices for {ticker}")
        t = t.reset_index().rename(columns={"Date": "price_date"})
        t["price_date"] = pd.to_datetime(t["price_date"]).dt.date.astype(str)
        t.insert(0, "ticker", ticker)
        parts.append(t)

    df = pd.concat(parts, ignore_index=True)
    if (df["close"] <= 0).any():
        raise IndexPriceError("Non-positive closing price found")
    if df.duplicated(["ticker", "price_date"]).any():
        raise IndexPriceError("Duplicate (ticker, price_date) rows")
    return df


def fetch_index_prices(start: date, end: date) -> pd.DataFrame:
    """Download daily prices for start..end (both included)."""
    import yfinance as yf  # imported here so tests of to_long() don't need it

    raw = yf.download(
        list(TICKERS),
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),  # yfinance's end is exclusive
        auto_adjust=False,
        group_by="ticker",
        progress=False,
    )
    return to_long(raw)


def write_parquet(df: pd.DataFrame, out_dir: Path, run_date: date) -> Path:
    out = df.copy()
    out["run_date"] = run_date.isoformat()
    out["ingested_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    folder = out_dir / f"run_date={run_date:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "index_prices.parquet"
    out.to_parquet(path, index=False)
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract Nifty 50 and Sensex prices to local Parquet.")
    parser.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (default: 7 days ago)")
    parser.add_argument("--end", type=date.fromisoformat, help="YYYY-MM-DD (default: today)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_date = date.today()
    end = args.end or run_date
    start = args.start or end - timedelta(days=LOOKBACK_DAYS)

    path = write_parquet(fetch_index_prices(start, end), args.out, run_date)
    logger.info("wrote %s (%d rows)", path, len(pd.read_parquet(path)))


if __name__ == "__main__":
    main()