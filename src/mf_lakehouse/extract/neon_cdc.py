"""Change data capture from Neon: extract only the schemes whose updated_at moved.

The watermark is the position of the last row extracted, in (updated_at, scheme_code)
order, kept in S3 so it survives restarts. The next run reads only rows after it.
Using scheme_code as a tie-breaker matters: the scheme_master loader updates many rows
in one transaction, so they share one updated_at.

Why not "re-read the last 5 minutes" (an overlap window)? Tested on 7 Nov 2026: because a
bulk load gives every row the same updated_at, the overlap re-read all rows on every run.

Known limitation: a transaction that commits after a CDC run but carries an older
updated_at would be missed. Only the loader writes scheme_master, its transactions take
seconds, and CDC runs after it, so this does not happen in this pipeline.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mf_lakehouse.common.config import PROJECT_ROOT, get_env
from mf_lakehouse.load.scheme_master import COLUMNS

logger = logging.getLogger(__name__)

STATE_KEY = "state/scheme_master_cdc.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "landing" / "scheme_master_cdc"

Watermark = tuple[datetime, str]  # (updated_at, scheme_code) of the last row extracted


def read_watermark(s3, bucket: str) -> Watermark | None:
    """The saved watermark, or None on the very first run."""
    from botocore.exceptions import ClientError

    try:
        body = s3.get_object(Bucket=bucket, Key=STATE_KEY)["Body"].read()
    except ClientError as err:
        if err.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise
    state = json.loads(body)
    return datetime.fromisoformat(state["updated_at"]), state["scheme_code"]


def write_watermark(s3, bucket: str, watermark: Watermark) -> None:
    updated_at, scheme_code = watermark
    body = json.dumps({
        "updated_at": updated_at.isoformat(),
        "scheme_code": scheme_code,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    })
    s3.put_object(Bucket=bucket, Key=STATE_KEY, Body=body.encode())


def new_watermark(changes: pd.DataFrame, old: Watermark | None) -> Watermark | None:
    """Position of the last row read (rows arrive sorted); unchanged when nothing was read."""
    if changes.empty:
        return old
    last = changes.iloc[-1]
    return last["updated_at"].to_pydatetime(), str(last["scheme_code"])


def changes_sql(watermark: Watermark | None) -> tuple[str, tuple]:
    cols = ", ".join([*COLUMNS, "created_at", "updated_at"])
    sql = f"SELECT {cols} FROM scheme_master"
    params: tuple = ()
    if watermark is not None:
        sql += " WHERE (updated_at, scheme_code) > (%s, %s)"
        params = watermark
    return sql + " ORDER BY updated_at, scheme_code", params


def fetch_changes(conninfo: str, watermark: Watermark | None) -> pd.DataFrame:
    import psycopg

    sql, params = changes_sql(watermark)
    with psycopg.connect(conninfo) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        names = [d.name for d in cur.description]
    df = pd.DataFrame(rows, columns=names)
    for col in ("created_at", "updated_at"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


def write_parquet(df: pd.DataFrame, out_dir: Path, extracted_at: datetime) -> Path:
    """One new file per run, never overwritten: two runs on one day must not erase each other."""
    out = df.copy()
    out["extracted_at"] = extracted_at.isoformat(timespec="seconds")
    folder = out_dir / f"run_date={extracted_at:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"changes_{extracted_at:%Y%m%dT%H%M%SZ}.parquet"
    out.to_parquet(path, index=False)
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract changed schemes from Neon (CDC) to local Parquet.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from mf_lakehouse.common.s3 import make_client

    s3, bucket = make_client(), get_env("S3_BUCKET_NAME")
    watermark = read_watermark(s3, bucket)
    changes = fetch_changes(get_env("NEON_SOURCE_URL"), watermark)
    logger.info("watermark %s: %d changed schemes", watermark, len(changes))

    if changes.empty:
        logger.info("no changes; watermark unchanged")
        return
    path = write_parquet(changes, args.out, datetime.now(timezone.utc))  # data first...
    watermark = new_watermark(changes, watermark)
    write_watermark(s3, bucket, watermark)                              # ...then the bookmark
    logger.info("wrote %s; watermark now %s", path, watermark)


if __name__ == "__main__":
    main()
