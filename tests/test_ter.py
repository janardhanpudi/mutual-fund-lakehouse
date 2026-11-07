from datetime import date

import pandas as pd
import pytest

from mf_lakehouse.extract.ter import (
    COLUMN_MAP,
    TerParseError,
    check_spreadsheet,
    parse_ter_frame,
    previous_month,
)

RAW_COLUMNS = list(COLUMN_MAP)  # the 15 header texts as AMFI writes them


def row(code, day, total=2.19):
    """One TER row; the four components add up to `total`."""
    parts = [total - 0.41, 0.03, 0.0, 0.38]
    return [code, "Sample Fund", "Open Ended", "Hybrid Schemes - Balanced Hybrid Fund",
            pd.Timestamp(f"2026-10-{day:02d}"), *parts, total, *parts, total]


def sheet(*rows):
    """A table shaped like pd.read_excel() of the TER download, with the disclaimer at the end."""
    disclaimer = [[None] * 15, ["Disclaimer :"] + [None] * 14, ["5. Percentages mentioned above are annualized."] + [None] * 14]
    return pd.DataFrame([*rows, *disclaimer], columns=RAW_COLUMNS)


def test_disclaimer_rows_are_dropped():
    df = parse_ter_frame(sheet(row("ABCD/O/O/X/01", 1), row("ABCD/O/O/X/01", 2)))
    assert len(df) == 2
    assert df["ter_date"].tolist() == ["2026-10-01", "2026-10-02"]


def test_stray_character_in_code_is_cleaned():
    # Like HDFC/O/O/OET/21/12/0093? and ...0093 on different days: one scheme
    df = parse_ter_frame(sheet(row("HDFC/O/O/OET/21/12/0093?", 1), row("HDFC/O/O/OET/21/12/0093", 2)))
    assert df["nsdl_scheme_code"].unique().tolist() == ["HDFC/O/O/OET/21/12/0093"]


def test_duplicate_after_cleaning_raises():
    with pytest.raises(TerParseError, match="duplicate"):
        parse_ter_frame(sheet(row("HDFC/O/O/OET/21/12/0093?", 1), row("HDFC/O/O/OET/21/12/0093", 1)))


def test_missing_column_raises():
    with pytest.raises(TerParseError, match="Missing columns"):
        parse_ter_frame(sheet(row("A/1", 1)).drop(columns=["TER Date"]))


def test_high_ber_is_kept_with_a_warning(caplog):
    with caplog.at_level("WARNING"):
        df = parse_ter_frame(sheet(row("A/1", 1, total=45.44)))
    assert df["regular_ber_pct"].iloc[0] == 45.03
    assert "base expense ratio above 2.5%" in caplog.text


def test_html_instead_of_spreadsheet_raises():
    with pytest.raises(TerParseError, match="Expected an .xlsx"):
        check_spreadsheet(b"<html>Service unavailable</html>")


def test_previous_month_crosses_year():
    assert previous_month(date(2027, 1, 1)) == date(2026, 12, 1)
    assert previous_month(date(2026, 11, 1)) == date(2026, 10, 1)
