"""AMFI total expense ratio (TER): one Excel download per month, daily rows.

Rules from the Day 2 exploration of October 2026:
- `excel=true` returns the whole month in one request (paginated JSON is capped at 100 rows)
- the file ends with blank and disclaimer rows (no TER Date) -> dropped
- scheme codes can carry stray characters (HDFC ...0093?) -> cleaned to letters, digits, '/'
- late rows keep arriving after the month ends -> fetch current and previous month every run
"""

from __future__ import annotations

import argparse
import io
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from mf_lakehouse.common.config import PROJECT_ROOT
from mf_lakehouse.common.http import get

logger = logging.getLogger(__name__)

TER_URL = "https://www.amfiindia.com/api/populate-te-rdata-revised"
DEFAULT_OUT = PROJECT_ROOT / "data" / "landing" / "ter"
MAX_PLAUSIBLE_BER = 2.5  # % per year; SEBI caps the base expense ratio. Totals can be higher
                         # because trading costs are annualized (seen on new funds in Oct 2026).

COMPONENTS = {
    "Base Expense Ratio (BER) (%)": "ber_pct",
    "Brokerage cost (%)": "brokerage_pct",
    "Transaction Cost incurred for the purpose of execution of trade (%)": "transaction_cost_pct",
    "Statutory Levies (including GST) (%)": "statutory_levies_pct",
    "Total TER (%)": "total_ter_pct",
}
COLUMN_MAP = {
    "NSDL Scheme Code": "nsdl_scheme_code",
    "Scheme Name": "scheme_name",
    "Scheme Type": "scheme_type",
    "Scheme Category": "scheme_category",
    "TER Date": "ter_date",
    **{f"{plan} Plan - {raw}": f"{plan.lower()}_{name}" for plan in ("Regular", "Direct") for raw, name in COMPONENTS.items()},
}
NUM_COLS = [name for name in COLUMN_MAP.values() if name.endswith("_pct")]


class TerParseError(ValueError):
    """The TER data does not match the layout this extractor expects."""


def check_spreadsheet(content: bytes) -> bytes:
    """An .xlsx file is a zip archive, so it always starts with 'PK'."""
    if not content.startswith(b"PK"):
        raise TerParseError(f"Expected an .xlsx file, got: {content[:80]!r}")
    return content


def fetch_ter_xlsx(month: date) -> bytes:
    """Download one month of TER as .xlsx."""
    resp = get(
        TER_URL,
        params={"MF_ID": "All", "Month": f"{month:%m-%Y}", "strCat": "-1", "strType": "-1", "excel": "true"},
        timeout=300,
    )
    return check_spreadsheet(resp.content)


def parse_ter_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Clean the sheet as read by pandas: map columns, drop disclaimer rows, clean codes, check keys."""
    raw = raw.rename(columns=lambda c: " ".join(str(c).split()))
    missing = [c for c in COLUMN_MAP if c not in raw.columns]
    if missing:
        raise TerParseError(f"Missing columns: {missing}")
    df = raw[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)

    df = df[df["ter_date"].notna()].copy()  # blank + disclaimer rows have no date
    if df.empty:
        raise TerParseError("No TER rows found")

    df["nsdl_scheme_code"] = df["nsdl_scheme_code"].astype(str).str.replace(r"[^A-Za-z0-9/]", "", regex=True)
    df["ter_date"] = pd.to_datetime(df["ter_date"]).dt.date.astype(str)

    for col in NUM_COLS:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().any():
            raise TerParseError(f"{values.isna().sum()} non-numeric values in {col}")
        df[col] = values

    dup = df.duplicated(["nsdl_scheme_code", "ter_date"], keep=False)
    if dup.any():
        raise TerParseError(f"{dup.sum()} duplicate (nsdl_scheme_code, ter_date) rows after cleaning codes")

    high = (df[["regular_ber_pct", "direct_ber_pct"]] > MAX_PLAUSIBLE_BER).any(axis=1)
    if high.any():
        logger.warning("%d rows have a base expense ratio above %.1f%%; kept as-is", high.sum(), MAX_PLAUSIBLE_BER)
    return df.reset_index(drop=True)



def read_ter_xlsx(content: bytes) -> pd.DataFrame:
    return parse_ter_frame(pd.read_excel(io.BytesIO(content)))


def previous_month(month: date) -> date:
    return date(month.year - 1, 12, 1) if month.month == 1 else date(month.year, month.month - 1, 1)


def write_parquet(df: pd.DataFrame, out_dir: Path, month: date, run_date: date) -> Path:
    out = df.copy()
    out["ter_month"] = f"{month:%Y-%m}"
    out["run_date"] = run_date.isoformat()
    out["ingested_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    folder = out_dir / f"ter_month={month:%Y-%m}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "ter.parquet"
    out.to_parquet(path, index=False)  # same month -> same file, overwritten
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract AMFI TER to local Parquet (current and previous month).")
    parser.add_argument("--month", help="one month as YYYY-MM (default: current and previous month)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_date = date.today()
    if args.month:
        months = [datetime.strptime(args.month, "%Y-%m").date()]
    else:
        this_month = run_date.replace(day=1)
        months = [previous_month(this_month), this_month]

    for month in months:
        df = read_ter_xlsx(fetch_ter_xlsx(month))
        path = write_parquet(df, args.out, month, run_date)
        logger.info("wrote %s (%d rows, %d schemes)", path, len(df), df["nsdl_scheme_code"].nunique())


if __name__ == "__main__":
    main()
