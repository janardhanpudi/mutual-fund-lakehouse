"""AMFI NAV extractor.

Parses both AMFI NAV text layouts into one table:
- the daily file (NAVAll.txt): latest NAV per scheme
- the NAV history report: one NAV per scheme per date

Bronze keeps raw values, so parsing is structural only: split lines, carry
the category and fund-house headings down to each row, and map column names.
Cleaning (ISIN '-', option labels, category spacing) happens in silver (dbt).
Anything unexpected raises NavParseError instead of writing bad data.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

# Header text in either layout -> our column name.
COLUMN_MAP = {
    "Scheme Code": "scheme_code",
    "Scheme Name": "scheme_name",  # daily file
    "NAV Name": "scheme_name",  # history file
    "ISIN Div Payout/ ISIN Growth": "isin_growth_or_payout",  # daily file
    "ISIN Div Payout/ISIN Growth": "isin_growth_or_payout",  # history file
    "ISIN Div Reinvestment": "isin_reinvestment",
    "Plan": "plan",
    "Option": "option",
    "Net Asset Value": "nav",
    "Date": "nav_date",
}

DATA_COLUMNS = [
    "scheme_code",
    "scheme_name",
    "plan",
    "option",
    "isin_growth_or_payout",
    "isin_reinvestment",
    "nav",
    "nav_date",
]
OUTPUT_COLUMNS = DATA_COLUMNS + ["category_raw", "amc"]

CATEGORY_RE = re.compile(r"^(Open Ended|Close Ended|Interval Fund)\s+Schemes", re.IGNORECASE)
NAV_DATE_FORMAT = "%d-%b-%Y"


class NavParseError(ValueError):
    """The NAV text does not match the layout this parser expects."""


def parse_nav_text(text: str) -> pd.DataFrame:
    """Parse AMFI NAV text (daily or history layout) into a raw-valued table."""
    lines = text.lstrip("﻿").splitlines()

    header_idx = next((i for i, line in enumerate(lines) if line.strip()), None)
    if header_idx is None:
        raise NavParseError("Empty NAV file")

    header = [h.strip() for h in lines[header_idx].split(";")]
    unknown = [h for h in header if h not in COLUMN_MAP]
    if unknown:
        raise NavParseError(f"Unknown columns: {unknown}")
    mapped = [COLUMN_MAP[h] for h in header]
    if sorted(mapped) != sorted(DATA_COLUMNS):
        raise NavParseError(f"Header does not have the expected columns: {header}")

    rows: list[list[str | None]] = []
    category: str | None = None
    amc: str | None = None

    for line_no, line in enumerate(lines[header_idx + 1 :], start=header_idx + 2):
        s = line.strip()
        if not s:
            continue
        if ";" in s:
            parts = [p.strip() for p in s.split(";")]
            if len(parts) != len(header):
                raise NavParseError(
                    f"Line {line_no}: expected {len(header)} fields, got {len(parts)}: {s!r}"
                )
            rows.append(parts + [category, amc])
        elif CATEGORY_RE.match(s):
            category = s
        else:
            amc = s

    df = pd.DataFrame(rows, columns=mapped + ["category_raw", "amc"])
    df = df[OUTPUT_COLUMNS]
    _validate(df)
    return df


def _examples(df: pd.DataFrame, mask: pd.Series, cols: list[str]) -> str:
    return df.loc[mask, cols].head(5).to_dict("records").__repr__()


def _validate(df: pd.DataFrame) -> None:
    if df.empty:
        raise NavParseError("No data rows found")

    bad_code = ~df["scheme_code"].str.fullmatch(r"\d+")
    if bad_code.any():
        raise NavParseError(
            f"{bad_code.sum()} non-numeric scheme codes, e.g. "
            f"{_examples(df, bad_code, ['scheme_code', 'scheme_name'])}"
        )

    nav = pd.to_numeric(df["nav"], errors="coerce")
    bad_nav = nav.isna() | (nav < 0)
    if bad_nav.any():
        raise NavParseError(
            f"{bad_nav.sum()} rows with a missing, non-numeric or negative NAV, e.g. "
            f"{_examples(df, bad_nav, ['scheme_code', 'nav', 'nav_date'])}"
        )

    # Zero is legitimate: AMFI publishes 0 for written-off segregated portfolios
    # (241 rows in the 1 Nov 2026 file). Kept in bronze, excluded from returns in silver.
    zero_nav = nav == 0
    if zero_nav.any():
        logger.warning("%d rows have a NAV of 0 (segregated portfolios); kept as-is", zero_nav.sum())

    dates = pd.to_datetime(df["nav_date"], format=NAV_DATE_FORMAT, errors="coerce")
    bad_date = dates.isna()
    if bad_date.any():
        raise NavParseError(
            f"{bad_date.sum()} rows with an unreadable date, e.g. "
            f"{_examples(df, bad_date, ['scheme_code', 'nav_date'])}"
        )

    dup = df.duplicated(["scheme_code", "nav_date"], keep=False)
    if dup.any():
        raise NavParseError(
            f"{dup.sum()} rows share a (scheme_code, nav_date), e.g. "
            f"{_examples(df, dup, ['scheme_code', 'nav_date', 'nav'])}"
        )

    no_amc = df["amc"].isna()
    if no_amc.any():
        raise NavParseError(
            f"{no_amc.sum()} rows appear before any fund-house heading, e.g. "
            f"{_examples(df, no_amc, ['scheme_code', 'scheme_name'])}"
        )
