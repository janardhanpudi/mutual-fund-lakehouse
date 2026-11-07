"""Upsert scheme details from the latest daily NAV landing file into Neon (scheme_master).

Only rows whose details actually changed are updated, so updated_at moves only on
real changes. That is what lets a later CDC step ask "what changed since my last run?".
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from mf_lakehouse.common.config import PROJECT_ROOT, get_env

logger = logging.getLogger(__name__)

DAILY_DIR = PROJECT_ROOT / "data" / "landing" / "nav" / "source=daily"
KEY = "scheme_code"
ATTRIBUTES = [
    "scheme_name",
    "plan",
    "option",
    "isin_growth_or_payout",
    "isin_reinvestment",
    "category_raw",
    "amc",
]
COLUMNS = [KEY, *ATTRIBUTES]


def latest_daily_file(daily_dir: Path = DAILY_DIR) -> Path:
    """The newest run_date=YYYY-MM-DD/nav.parquet (ISO dates sort correctly as text)."""
    files = sorted(daily_dir.glob("run_date=*/nav.parquet"))
    if not files:
        raise FileNotFoundError(f"No daily NAV files under {daily_dir}; run the NAV extractor first")
    return files[-1]


def to_rows(df: pd.DataFrame) -> list[tuple]:
    """Scheme rows ready for the database: one per scheme_code, missing values as None."""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Daily NAV file is missing columns: {missing}")
    schemes = df[COLUMNS].drop_duplicates()
    if schemes[KEY].duplicated().any():
        raise ValueError("A scheme_code appears with two different sets of details in one file")
    schemes = schemes.astype(object).where(schemes.notna(), None)
    return list(schemes.itertuples(index=False, name=None))


def upsert_sql() -> str:
    cols = ", ".join(COLUMNS)
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in ATTRIBUTES)
    current = ", ".join(f"scheme_master.{c}" for c in ATTRIBUTES)
    incoming = ", ".join(f"EXCLUDED.{c}" for c in ATTRIBUTES)
    return f"""
        INSERT INTO scheme_master ({cols})
        SELECT {cols} FROM scheme_master_incoming
        ON CONFLICT ({KEY}) DO UPDATE SET {set_clause}
        WHERE ({current}) IS DISTINCT FROM ({incoming})
        RETURNING (xmax = 0) AS inserted
    """


def upsert(rows: list[tuple], conninfo: str) -> dict[str, int]:
    """Bulk-load rows into a temp table, then insert new / update changed schemes."""
    import psycopg

    with psycopg.connect(conninfo) as conn, conn.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE scheme_master_incoming "
            "(LIKE scheme_master INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with cur.copy(f"COPY scheme_master_incoming ({', '.join(COLUMNS)}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        cur.execute(upsert_sql())
        flags = [inserted for (inserted,) in cur.fetchall()]

    inserted = sum(flags)
    updated = len(flags) - inserted
    return {"inserted": inserted, "updated": updated, "unchanged": len(rows) - inserted - updated}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Upsert scheme details into Neon scheme_master.")
    parser.add_argument("--file", type=Path, help="daily NAV parquet (default: latest run_date)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    path = args.file or latest_daily_file()
    rows = to_rows(pd.read_parquet(path))
    counts = upsert(rows, get_env("NEON_SOURCE_URL"))
    logger.info("%s: %d schemes -> inserted %d, updated %d, unchanged %d",
                path.parent.name, len(rows), counts["inserted"], counts["updated"], counts["unchanged"])


if __name__ == "__main__":
    main()
