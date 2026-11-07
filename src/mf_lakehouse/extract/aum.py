"""AMFI monthly AUM report (legacy .xls), category level.

Rules from the Day 2 exploration of the September 2026 report:
- data rows are coded with lowercase Roman numerals (i, ii, ...); everything else
  (headings, subtotals, totals, footnotes) is skipped
- type rows are A/B/C, class rows are uppercase numerals; a new type resets the class
- columns are found by pattern, because the header text contains the month
- the parsed rows must add up to the report's own totals, or the run fails
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from mf_lakehouse.common.config import PROJECT_ROOT
from mf_lakehouse.common.http import get

logger = logging.getLogger(__name__)

SHEET = "MCR_MonthlyReport"
AUM_URL = "https://portal.amfiindia.com/spages/am{mon}{year}repo.xls"  # e.g. amsep2026repo.xls
XLS_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")  # first bytes of every legacy .xls file
DEFAULT_OUT = PROJECT_ROOT / "data" / "landing" / "aum"

# Header text starts with ... -> column name (checked in this order)
COLUMN_PATTERNS = [
    ("no. of schemes", "num_schemes"),
    ("no. of folios", "num_folios"),
    ("funds mobilized", "funds_mobilized_inr_cr"),
    ("repurchase/redemption", "redemption_inr_cr"),
    ("net inflow", "net_flow_inr_cr"),
    ("net assets under management as on", "net_aum_inr_cr"),
    ("average net assets", "avg_net_aum_inr_cr"),
    ("no. of segregated", "segregated_portfolios"),
    ("net assets under management in segregated", "segregated_net_aum_inr_cr"),
]
NUM_COLS = [name for _, name in COLUMN_PATTERNS]
TYPE_CODES = {"A", "B", "C"}
MONTH_RE = re.compile(r"month of\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
TOTAL_RE = re.compile(r"^total\s*([ABC])\b", re.IGNORECASE)
TOLERANCE = 0.01  # INR crore


class AumParseError(ValueError):
    """The AUM report does not match the layout this parser expects."""


def _text(value) -> str:
    return " ".join(str(value).split())


def _clean_name(value) -> str:
    return re.sub(r"[#*]+", "", _text(value)).strip()


def _report_month(title_rows: list[list]) -> date:
    for row in title_rows:
        m = MONTH_RE.search(" ".join(_text(v) for v in row))
        if m:
            return datetime.strptime(f"1 {m.group(1)} {m.group(2)}", "%d %B %Y").date()
    raise AumParseError("Report month not found in the title rows")


def _header(rows: list[list]) -> tuple[int, dict[int, str]]:
    """Find the header row and map column positions to our names."""
    for idx, row in enumerate(rows[:10]):
        if len(row) > 1 and _text(row[1]).lower().startswith("scheme name"):
            mapping = {}
            for pos, cell in enumerate(row[2:], start=2):
                text = _text(cell).lower()
                match = next((name for prefix, name in COLUMN_PATTERNS if text.startswith(prefix)), None)
                if match:
                    mapping[pos] = match
            found = sorted(mapping.values())
            if found != sorted(NUM_COLS):
                missing = set(NUM_COLS) - set(found)
                raise AumParseError(f"Header columns missing or repeated: missing={sorted(missing)}, found={found}")
            return idx, mapping
    raise AumParseError("Header row ('Scheme Name') not found")


def _numbers(row: list, mapping: dict[int, str], row_no: int) -> dict[str, float]:
    out = {}
    for pos, name in mapping.items():
        value = row[pos] if pos < len(row) else ""
        if isinstance(value, str):
            raise AumParseError(f"Row {row_no}: text {value!r} in numeric column {name}")
        out[name] = float(value)
    return out


def parse_aum_rows(rows: list[list]) -> pd.DataFrame:
    """Parse the sheet's rows (lists of cell values) into one row per category."""
    header_idx, mapping = _header(rows)
    month = _report_month(rows[:header_idx])  # title only: the header also mentions the month

    records, totals = [], {}
    scheme_type = scheme_class = None
    for row_no, row in enumerate(rows[header_idx + 1 :], start=header_idx + 1):
        if len(row) < 2:
            continue
        code, name = _text(row[0]), _clean_name(row[1])
        if code in TYPE_CODES:
            scheme_type, scheme_class = name, None
        elif re.fullmatch(r"[IVX]+", code):
            scheme_class = name
        elif re.fullmatch(r"[ivx]+", code):
            records.append({"scheme_type": scheme_type, "scheme_class": scheme_class,
                            "category": name, **_numbers(row, mapping, row_no)})
        elif name.lower() == "grand total":
            totals["grand"] = _numbers(row, mapping, row_no)
        elif TOTAL_RE.match(name):
            totals[TOTAL_RE.match(name).group(1).upper()] = _numbers(row, mapping, row_no)

    if not records:
        raise AumParseError("No category rows found")
    df = pd.DataFrame(records)
    df.insert(0, "report_month", month.isoformat())

    if df.duplicated(["scheme_type", "scheme_class", "category"]).any():
        raise AumParseError("Duplicate (scheme_type, scheme_class, category)")
    _check_totals(df, totals)
    return df


def _check_totals(df: pd.DataFrame, totals: dict[str, dict]) -> None:
    """Leaf rows must add up to the report's Grand Total and Total A/B/C."""
    if "grand" not in totals:
        raise AumParseError("Grand Total row not found")
    type_letter = {"open": "A", "close": "B", "interval": "C"}
    checks = {"Grand Total": (df, totals["grand"])}
    for letter in ("A", "B", "C"):
        if letter in totals:
            part = df[df["scheme_type"].str.lower().str.split().str[0].map(type_letter) == letter]
            checks[f"Total {letter}"] = (part, totals[letter])
    for label, (part, expected) in checks.items():
        diff = (part[NUM_COLS].sum() - pd.Series(expected)).abs()
        if (diff > TOLERANCE).any():
            raise AumParseError(f"{label}: categories do not add up, worst column {diff.idxmax()} off by {diff.max():,.2f}")


def aum_url(month: date) -> str:
    return AUM_URL.format(mon=month.strftime("%b").lower(), year=month.year)


def fetch_aum_xls(month: date) -> bytes | None:
    """Download one month's report, or None if AMFI has not published it yet (404)."""
    try:
        content = get(aum_url(month)).content
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 404:
            return None
        raise
    if not content.startswith(XLS_SIGNATURE):
        raise AumParseError(f"Expected a legacy .xls file from {aum_url(month)}, got: {content[:80]!r}")
    return content


def read_aum_xls(source: Path | bytes) -> pd.DataFrame:
    """Read the legacy .xls report (a file path or downloaded bytes) and parse its MCR sheet."""
    import xlrd

    book = xlrd.open_workbook(file_contents=source) if isinstance(source, bytes) else xlrd.open_workbook(source)
    sheet = book.sheet_by_name(SHEET)
    return parse_aum_rows([sheet.row_values(r) for r in range(sheet.nrows)])


def previous_month(day: date) -> date:
    first = day.replace(day=1)
    return date(first.year - 1, 12, 1) if first.month == 1 else date(first.year, first.month - 1, 1)


def write_parquet(df: pd.DataFrame, out_dir: Path, run_date: date) -> Path:
    out = df.copy()
    out["run_date"] = run_date.isoformat()
    out["ingested_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    folder = out_dir / f"report_month={df['report_month'].iloc[0][:7]}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "aum.parquet"
    out.to_parquet(path, index=False)  # same month -> same file, overwritten
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download and parse an AMFI monthly AUM report to local Parquet.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--month", help="report month YYYY-MM (default: last month)")
    source.add_argument("--file", type=Path, help="parse an already downloaded .xls instead")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_date = date.today()

    if args.file:
        df = read_aum_xls(args.file)
    else:
        month = datetime.strptime(args.month, "%Y-%m").date() if args.month else previous_month(run_date)
        content = fetch_aum_xls(month)
        if content is None:
            logger.info("AUM report for %s is not published yet (%s); nothing to do", f"{month:%Y-%m}", aum_url(month))
            return
        df = read_aum_xls(content)

    path = write_parquet(df, args.out, run_date)
    logger.info("wrote %s (%d categories, totals checked)", path, len(df))


if __name__ == "__main__":
    main()
