"""Mutual Fund Lakehouse dashboard. Reads the gold tables published to Neon (schema mf_serving).

Run from the project root:
    uv run --env-file .env streamlit run app/dashboard.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

from mf_lakehouse.common.config import get_env

SCHEMA = "mf_serving"
TEAL = "#0F766E"
PALETTE = ["#0F766E", "#2563EB", "#D97706", "#DB2777", "#7C3AED", "#059669", "#DC2626", "#0891B2"]
MAX_VOLATILITY_SHOWN = 80

st.set_page_config(page_title="Mutual Fund Lakehouse", page_icon="📈", layout="wide")

st.markdown(
    """
<style>
.hero {background: linear-gradient(135deg, #0F766E, #2563EB); color: white;
       padding: 28px 32px; border-radius: 18px; margin-bottom: 18px;}
.hero h1 {color: white; margin: 0; font-size: 2.1rem;}
.hero p {margin: 6px 0 0 0; opacity: 0.92;}
.kpi {background: white; border-radius: 14px; padding: 16px 18px;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08); border-left: 5px solid #0F766E;}
.kpi .label {color: #64748B; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em;}
.kpi .value {color: #0F172A; font-size: 1.7rem; font-weight: 700; margin-top: 4px;}
.kpi .sub {color: #64748B; font-size: 0.8rem;}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine():
    url = get_env("NEON_READER_URL").replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=3600)
def load(table: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(f"select * from {SCHEMA}.{table}"), conn)


def kpi(label: str, value: str, sub: str = "") -> str:
    return f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'


bench = load("fct_scheme_vs_benchmark")
risk = load("fct_scheme_risk")
ranks = load("fct_category_rankings")

full = bench.merge(
    risk[["scheme_code", "volatility_1y_pct", "max_drawdown_1y_pct"]], on="scheme_code", how="left"
)
full["scheme_class"] = full["scheme_class"].fillna("Other")
growth = full[full["option_type"] == "Growth"]

as_of = pd.to_datetime(full["latest_nav_date"]).max().date()
equity_growth = growth[(growth["scheme_class"] == "Equity Schemes") & growth["excess_return_1y_pct"].notna()]
beat_share = (equity_growth["excess_return_1y_pct"] > 0).mean() * 100
median_1y = growth["return_1y_pct"].median()

st.markdown(
    f"""
<div class="hero">
  <h1>📈 Mutual Fund Lakehouse</h1>
  <p>Latest NAV: {as_of}. Returns are point-to-point. Excess return = fund minus the Nifty 50 price index.</p>
</div>
""",
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
c1.markdown(kpi("Active schemes", f"{len(full):,}", "with NAV in the last trading day"), unsafe_allow_html=True)
c2.markdown(kpi("Median 1Y return", f"{median_1y:.1f}%", "Growth options"), unsafe_allow_html=True)
c3.markdown(
    kpi("Equity beat Nifty (1Y)", f"{beat_share:.0f}%", f"{len(equity_growth):,} equity Growth schemes"),
    unsafe_allow_html=True,
)
c4.markdown(kpi("Ranked funds", f"{len(ranks):,}", "Growth, by category and plan"), unsafe_allow_html=True)

tab_explore, tab_rank, tab_risk, tab_detail = st.tabs(
    ["Explore", "Category rankings", "Risk vs return", "Fund detail"]
)

with tab_explore:
    f1, f2, f3 = st.columns([3, 2, 1])
    query = f1.text_input("Search by scheme name", placeholder="e.g. Flexi Cap, Liquid, Nippon")
    plans = f2.multiselect("Plan", ["Direct Plan", "Regular Plan"], default=["Direct Plan", "Regular Plan"])
    growth_only = f3.checkbox("Growth only", value=True)

    df = growth if growth_only else full
    df = df[df["plan"].isin(plans)]
    if query:
        df = df[df["scheme_name"].str.contains(query, case=False, na=False)]

    st.caption(f"{len(df):,} schemes")
    st.dataframe(
        df[
            ["scheme_name", "plan", "category", "latest_nav", "return_1y_pct",
             "nifty50_return_1y_pct", "excess_return_1y_pct", "volatility_1y_pct", "max_drawdown_1y_pct"]
        ].sort_values("return_1y_pct", ascending=False),
        hide_index=True,
        column_config={
            "scheme_name": st.column_config.TextColumn("Scheme", width="large"),
            "latest_nav": st.column_config.NumberColumn("NAV", format="%.4f"),
            "return_1y_pct": st.column_config.NumberColumn("1Y return", format="%.2f%%"),
            "nifty50_return_1y_pct": st.column_config.NumberColumn("Nifty 1Y", format="%.2f%%"),
            "excess_return_1y_pct": st.column_config.NumberColumn("Excess 1Y", format="%+.2f%%"),
            "volatility_1y_pct": st.column_config.NumberColumn("Volatility", format="%.1f%%"),
            "max_drawdown_1y_pct": st.column_config.NumberColumn("Max drawdown", format="%.1f%%"),
        },
    )

with tab_rank:
    left, right = st.columns([2, 1])
    category = left.selectbox("Category", sorted(ranks["category"].dropna().unique()))
    plan = right.radio("Plan", ["Direct Plan", "Regular Plan"], horizontal=True)
    cat_df = ranks[(ranks["category"] == category) & (ranks["plan"] == plan)].sort_values("category_rank")

    top = cat_df.head(15)
    fig = px.bar(
        top,
        x="return_1y_pct",
        y="scheme_name",
        orientation="h",
        color="return_1y_pct",
        color_continuous_scale=["#FCA5A5", "#E2E8F0", "#5EEAD4", TEAL],
        labels={"return_1y_pct": "1Y return %", "scheme_name": ""},
        title=f"Top 15 in {category}",
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(coloraxis_showscale=False, height=520, margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        cat_df[["category_rank", "scheme_name", "amc", "return_1y_pct", "top_pct"]],
        hide_index=True,
        column_config={
            "category_rank": st.column_config.NumberColumn("Rank"),
            "return_1y_pct": st.column_config.NumberColumn("1Y return", format="%.2f%%"),
            "top_pct": st.column_config.NumberColumn("Top %", format="%.1f"),
        },
    )
    st.caption(f"{len(cat_df):,} Growth schemes. Rank 1 is the best 1-year return in this group.")

with tab_risk:
    scatter_df = growth[
        growth["return_1y_pct"].notna()
        & growth["volatility_1y_pct"].notna()
        & (growth["volatility_1y_pct"] <= MAX_VOLATILITY_SHOWN)
    ]
    fig = px.scatter(
        scatter_df,
        x="volatility_1y_pct",
        y="return_1y_pct",
        color="scheme_class",
        hover_name="scheme_name",
        hover_data={"plan": True, "category": True, "volatility_1y_pct": ":.1f", "return_1y_pct": ":.1f"},
        color_discrete_sequence=PALETTE,
        labels={"volatility_1y_pct": "Volatility, 1Y (%)", "return_1y_pct": "1Y return (%)", "scheme_class": "Class"},
        opacity=0.7,
        render_mode="svg",
    )
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Growth schemes, up to {MAX_VOLATILITY_SHOWN}% volatility. "
        "Up and to the left is the best trade-off: high return for low bumpiness."
    )

with tab_detail:
    search = st.text_input("Find a scheme", placeholder="Type part of the name")
    matches = full[full["scheme_name"].str.contains(search, case=False, na=False)] if search else full
    matches = matches.head(200)
    if matches.empty:
        st.info("No scheme matches that name.")
    else:
        code = st.selectbox(
            "Scheme",
            matches["scheme_code"],
            format_func=lambda c: (
                f"{matches.loc[matches['scheme_code'] == c, 'scheme_name'].iloc[0]} "
                f"({matches.loc[matches['scheme_code'] == c, 'plan'].iloc[0]})"
            ),
        )
        row = full[full["scheme_code"] == code].iloc[0]
        periods = ["1M", "3M", "6M", "1Y"]
        chart_df = pd.DataFrame(
            {
                "Period": periods * 2,
                "Return %": [row.return_1m_pct, row.return_3m_pct, row.return_6m_pct, row.return_1y_pct,
                             row.nifty50_return_1m_pct, row.nifty50_return_3m_pct,
                             row.nifty50_return_6m_pct, row.nifty50_return_1y_pct],
                "Series": ["Fund"] * 4 + ["Nifty 50"] * 4,
            }
        )
        fig = px.bar(
            chart_df, x="Period", y="Return %", color="Series", barmode="group",
            color_discrete_map={"Fund": TEAL, "Nifty 50": "#94A3B8"},
            title=row.scheme_name,
        )
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=60, b=10))
        st.plotly_chart(fig, use_container_width=True)

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(kpi("Latest NAV", f"{row.latest_nav:.4f}", str(row.latest_nav_date)), unsafe_allow_html=True)
        k2.markdown(kpi("Volatility (1Y)", f"{row.volatility_1y_pct:.1f}%" if pd.notna(row.volatility_1y_pct) else "n/a"), unsafe_allow_html=True)
        k3.markdown(kpi("Max drawdown (1Y)", f"{row.max_drawdown_1y_pct:.1f}%" if pd.notna(row.max_drawdown_1y_pct) else "n/a"), unsafe_allow_html=True)
        k4.markdown(kpi("Category", str(row.category), str(row.scheme_class)), unsafe_allow_html=True)
