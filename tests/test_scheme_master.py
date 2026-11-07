import pandas as pd
import pytest

from mf_lakehouse.load.scheme_master import COLUMNS, latest_daily_file, to_rows, upsert_sql


def daily_frame(**changes):
    row = {
        "scheme_code": "135762", "scheme_name": "Axis Children's Fund", "plan": "Direct Plan",
        "option": "Growth Option", "isin_growth_or_payout": "INF846K01WO1", "isin_reinvestment": "-",
        "category_raw": "Open Ended Schemes(Children's Fund)", "amc": "Axis Mutual Fund",
        "nav": "29.1949", "nav_date": "30-Oct-2026", "source": "daily",
    }
    row.update(changes)
    return pd.DataFrame([row])


def test_latest_file_is_newest_run_date(tmp_path):
    for day in ["2026-11-06", "2026-11-07", "2026-10-31"]:
        f = tmp_path / f"run_date={day}" / "nav.parquet"
        f.parent.mkdir()
        f.write_bytes(b"")
    assert latest_daily_file(tmp_path).parent.name == "run_date=2026-11-07"


def test_no_daily_files_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="run the NAV extractor first"):
        latest_daily_file(tmp_path)


def test_rows_keep_only_scheme_columns_and_none_for_missing():
    rows = to_rows(daily_frame(category_raw=None))
    assert len(rows) == 1 and len(rows[0]) == len(COLUMNS)
    assert rows[0][0] == "135762"
    assert rows[0][COLUMNS.index("category_raw")] is None


def test_conflicting_details_for_one_code_raise():
    df = pd.concat([daily_frame(), daily_frame(scheme_name="Renamed Fund")])
    with pytest.raises(ValueError, match="two different sets of details"):
        to_rows(df)


def test_update_only_when_something_differs():
    sql = upsert_sql()
    assert "ON CONFLICT (scheme_code) DO UPDATE" in sql
    assert "IS DISTINCT FROM" in sql
