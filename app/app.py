"""Mutual fund dashboard. Reads the gold tables published to Neon (schema mf_serving)
with the read-only mf_app login. Run from the project root:

    uv run --env-file .env streamlit run app/app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from mf_lakehouse.common.config import get_env

SCHEMA = "mf_serving"
MAX_VOLATILITY_SHOWN = 80  # a few funds have extreme volatility from very short histories; keep the chart readable

st.set_page_config(page_title="Mutual Fund Lakehouse", layout="wide")


@st.cache_resource
def get_engine():
    url = get_env("NEON_READER_URL").replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=3600)
def load(table: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(f"select * from {SCHEMA}.{table}"), conn)


bench = load("fct_scheme_vs_benchmark")
risk = load("fct_scheme_risk")
ranks = load("fct_category_rankings")

st.title("Mutual Fund Lakehouse")
st.caption(
    f"Latest NAV date: {bench['latest_nav_date'].max()}. "
    "Returns are point-to-point. Excess return = fund minus Nifty 50 price index."
)

view = st.sidebar.radio("View", ["Scheme search", "Category rankings", "Risk vs return"])
growth_only = st.sidebar.checkbox("Growth options only", value=True)

if view == "Scheme search":
    query = st.text_input("Scheme name contains", "")
    df = bench.merge(
        risk[["scheme_code", "volatility_1y_pct", "max_drawdown_1y_pct"]], on="scheme_code", how="left"
    )
    if growth_only:
        df = df[df["option_type"] == "Growth"]
    if query:
        df = df[df["scheme_name"].str.contains(query, case=False, na=False)]
    columns = [
        "scheme_name", "plan", "category", "latest_nav",
        "return_1y_pct", "nifty50_return_1y_pct", "excess_return_1y_pct",
        "volatility_1y_pct", "max_drawdown_1y_pct",
    ]
    st.dataframe(df[columns].sort_values("return_1y_pct", ascending=False), hide_index=True)
    st.caption(f"{len(df):,} schemes")

elif view == "Category rankings":
    category = st.selectbox("Category", sorted(ranks["category"].dropna().unique()))
    plan = st.radio("Plan", ["Direct Plan", "Regular Plan"], horizontal=True)
    df = ranks[(ranks["category"] == category) & (ranks["plan"] == plan)].sort_values("category_rank")
    st.subheader("Top 10 by 1-year return")
    st.bar_chart(df.head(10).set_index("scheme_name")["return_1y_pct"])
    st.dataframe(
        df[["category_rank", "scheme_name", "amc", "return_1y_pct", "top_pct"]], hide_index=True
    )
    st.caption(f"{len(df):,} Growth schemes in this category and plan. Rank 1 is the best.")

else:
    df = bench.merge(risk[["scheme_code", "volatility_1y_pct"]], on="scheme_code")
    df = df[
        (df["option_type"] == "Growth")
        & df["return_1y_pct"].notna()
        & df["volatility_1y_pct"].notna()
        & (df["volatility_1y_pct"] <= MAX_VOLATILITY_SHOWN)
    ]
    st.caption(
        "Each dot is a Growth scheme: how bumpy it was over the year (across) against its 1-year return (up). "
        f"Schemes above {MAX_VOLATILITY_SHOWN}% volatility are left out."
    )
    st.scatter_chart(df, x="volatility_1y_pct", y="return_1y_pct")
    st.caption(f"{len(df):,} schemes shown")
