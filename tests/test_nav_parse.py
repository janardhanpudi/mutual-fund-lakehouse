from pathlib import Path

import pytest

from mf_lakehouse.extract.nav import OUTPUT_COLUMNS, NavParseError, parse_nav_text

FIXTURES = Path(__file__).parent / "fixtures"
DAILY_HEADER = (
    "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;"
    "Scheme Name;Plan;Option;Net Asset Value;Date"
)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def daily_text(*body: str) -> str:
    """A minimal daily-layout file: header, one category, one fund house, given rows."""
    return "\n".join(
        [DAILY_HEADER, " ", "Open Ended Schemes(Debt Scheme - Liquid Fund)", " ", "Test Mutual Fund", " ", *body]
    )


# --- The two real layouts ---------------------------------------------------


def test_daily_layout_parses_all_rows():
    df = parse_nav_text(read("nav_daily_sample.txt"))
    assert list(df.columns) == OUTPUT_COLUMNS
    assert len(df) == 4
    assert df["scheme_code"].tolist() == ["135762", "135765", "900001", "900002"]


def test_history_layout_parses_all_rows():
    df = parse_nav_text(read("nav_history_sample.txt"))
    assert list(df.columns) == OUTPUT_COLUMNS
    assert len(df) == 3
    row = df.iloc[0]
    assert row["scheme_name"] == "Aditya Birla Sun Life Multi-Cap Fund-Direct Growth"
    assert row["isin_growth_or_payout"] == "INF209KB1Y49"
    assert row["nav"] == "21.24"


def test_both_layouts_give_same_columns():
    daily = parse_nav_text(read("nav_daily_sample.txt"))
    hist = parse_nav_text(read("nav_history_sample.txt"))
    assert list(daily.columns) == list(hist.columns)


def test_headings_are_carried_down_to_rows():
    df = parse_nav_text(read("nav_daily_sample.txt")).set_index("scheme_code")
    assert df.loc["135762", "amc"] == "Axis Mutual Fund"
    assert df.loc["135762", "category_raw"].startswith("Open Ended Schemes(Children")
    assert df.loc["900001", "amc"] == "ASK MUTUAL FUND"
    assert df.loc["900002", "amc"] == "IL&FS Mutual Fund (IDF)"
    assert df.loc["900002", "category_raw"] == "Close Ended Schemes(Income)"


def test_raw_values_are_kept():
    df = parse_nav_text(read("nav_daily_sample.txt")).set_index("scheme_code")
    assert df.loc["135762", "isin_reinvestment"] == "-"  # cleaned in silver, not here
    assert df.loc["900002", "plan"] == ""
    assert df.loc["135762", "nav_date"] == "30-Oct-2026"


def test_byte_order_mark_is_ignored():
    df = parse_nav_text("﻿" + read("nav_daily_sample.txt"))
    assert len(df) == 4


# --- Fail loudly -------------------------------------------------------------


def test_empty_file_raises():
    with pytest.raises(NavParseError, match="Empty"):
        parse_nav_text("  \n \n")


def test_unknown_column_raises():
    text = daily_text("1;A;-;X;Direct Plan;Growth;10.0;30-Oct-2026").replace("Plan;Option", "Plan;Variant")
    with pytest.raises(NavParseError, match="Unknown columns"):
        parse_nav_text(text)


def test_wrong_field_count_raises_with_line_number():
    text = daily_text("1;A;-;X;Direct Plan;Growth;10.0;30-Oct-2026", "2;A;-;Y;Direct Plan;10.0;30-Oct-2026")
    with pytest.raises(NavParseError, match=r"Line 8: expected 8 fields, got 7"):
        parse_nav_text(text)


@pytest.mark.parametrize("bad_nav", ["N.A.", "", "-5.1"])
def test_bad_nav_raises(bad_nav):
    text = daily_text(f"1;A;-;X;Direct Plan;Growth;{bad_nav};30-Oct-2026")
    with pytest.raises(NavParseError, match="NAV"):
        parse_nav_text(text)


def test_zero_nav_is_kept_with_a_warning(caplog):
    # AMFI publishes 0.0000 for written-off segregated portfolios.
    text = daily_text("1;A;-;X (Segregated);Direct Plan;Growth;0.0000;30-Oct-2026")
    with caplog.at_level("WARNING"):
        df = parse_nav_text(text)
    assert df["nav"].tolist() == ["0.0000"]
    assert "NAV of 0" in caplog.text


def test_bad_date_raises():
    text = daily_text("1;A;-;X;Direct Plan;Growth;10.0;2026-10-30")
    with pytest.raises(NavParseError, match="unreadable date"):
        parse_nav_text(text)


def test_non_numeric_scheme_code_raises():
    text = daily_text("ABC1;A;-;X;Direct Plan;Growth;10.0;30-Oct-2026")
    with pytest.raises(NavParseError, match="scheme codes"):
        parse_nav_text(text)


def test_duplicate_code_and_date_raises():
    row = "1;A;-;X;Direct Plan;Growth;10.0;30-Oct-2026"
    with pytest.raises(NavParseError, match="share a"):
        parse_nav_text(daily_text(row, row))


def test_row_before_fund_house_heading_raises():
    text = "\n".join([DAILY_HEADER, "Open Ended Schemes(Debt Scheme - Liquid Fund)", "1;A;-;X;Direct Plan;Growth;10.0;30-Oct-2026"])
    with pytest.raises(NavParseError, match="fund-house heading"):
        parse_nav_text(text)

def test_fund_house_carries_over_into_new_category():
    text = "\n".join([
        DAILY_HEADER,
        "Open Ended Schemes(Debt Scheme - Liquid Fund)",
        "Test Mutual Fund",
        "1;A;-;X;Direct Plan;Growth;10.0;30-Oct-2026",
        "Open Ended Schemes(Debt Scheme - Medium Duration Fund)",
        "2;B;-;Y;Direct Plan;Growth;20.0;30-Oct-2026",
    ])
    df = parse_nav_text(text).set_index("scheme_code")
    assert df.loc["2", "amc"] == "Test Mutual Fund"
    assert df.loc["2", "category_raw"] == "Open Ended Schemes(Debt Scheme - Medium Duration Fund)"