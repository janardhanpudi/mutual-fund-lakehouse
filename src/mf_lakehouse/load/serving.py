"""Publish the gold tables from Databricks to Neon (schema mf_serving) for the Streamlit app.

Each run replaces the five tables in one transaction: if anything fails, the old
copy stays in place. Grants are re-applied after every replace, so the read-only
role keeps working.
"""

from __future__ import annotations

import argparse
import logging
from decimal import Decimal

import pandas as pd
from databricks import sql as dbsql
from sqlalchemy import create_engine, text

from mf_lakehouse.common.config import get_env

logger = logging.getLogger(__name__)

GOLD_TABLES = [
    "dim_scheme",
    "fct_scheme_returns",
    "fct_scheme_vs_benchmark",
    "fct_category_rankings",
    "fct_scheme_risk",
]
SERVING_SCHEMA = "mf_serving"
READER_ROLE = "mf_reader"


def decimals_to_float(df: pd.DataFrame) -> pd.DataFrame:
    """Databricks returns DECIMAL columns as Python Decimal objects; store them as numbers."""
    out = df.copy()
    for col in out.columns:
        if out[col].map(type).eq(Decimal).any():
            out[col] = out[col].astype(float)
    return out


def neon_url(raw: str) -> str:
    """SQLAlchemy needs the psycopg driver named in the URL."""
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


def read_gold(conn, table: str) -> pd.DataFrame:
    catalog = get_env("DATABRICKS_CATALOG")
    with conn.cursor() as cur:
        cur.execute(f"select * from {catalog}.gold.{table}")
        df = cur.fetchall_arrow().to_pandas()
    if df.empty:
        raise RuntimeError(f"gold.{table} is empty; not publishing it")
    return decimals_to_float(df)


def publish() -> None:
    engine = create_engine(neon_url(get_env("NEON_SERVING_URL")))
    with dbsql.connect(
        server_hostname=get_env("DATABRICKS_HOST"),
        http_path=get_env("DATABRICKS_HTTP_PATH"),
        access_token=get_env("DATABRICKS_TOKEN"),
    ) as dbx, engine.begin() as neon:
        for table in GOLD_TABLES:
            df = read_gold(dbx, table)
            df.to_sql(table, neon, schema=SERVING_SCHEMA, if_exists="replace", index=False)
            neon.execute(text(f"grant select on {SERVING_SCHEMA}.{table} to {READER_ROLE}"))
            logger.info("published %s.%s (%d rows)", SERVING_SCHEMA, table, len(df))


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description="Copy gold tables to Neon for the app.").parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    publish()


if __name__ == "__main__":
    main()
