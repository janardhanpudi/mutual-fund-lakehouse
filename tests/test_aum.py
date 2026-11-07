import pytest

from mf_lakehouse.extract.aum import AumParseError, parse_aum_rows

HEADER = [
    "Sr ", "Scheme Name ",
    "No. of Schemes as on September 30, 2026",
    "No. of Folios as on September 30, 2026",
    "Funds Mobilized for the month of September 2026 (INR in crore)",
    "Repurchase/Redemption for the month of September 2026 (INR in crore)",
    "Net Inflow (+ve)/Outflow (-ve) for the month of September 2026 (INR in crore)",
    "Net Assets Under Management as on September 30, 2026 (INR in crore)",
    "Average Net Assets Under Management for the month September 2026 (INR in crore)",
    "No. of segregated portfolios created as on September 30, 2026",
    "Net Assets Under Management in segregated portfolio as on September 30, 2026 (INR in crore)",
]


def nums(n):
    """Nine numeric cells, all equal to n (easy to add up in your head)."""
    return [float(n)] * 9


def report(**overrides):
    """A small report shaped like AMFI's MCR sheet."""
    rows = {
        "title": ["", "Monthly Report for the month of September 2026 "],
        "header": HEADER,
        "A": ["A", "Open ended Schemes"],
        "I": ["I", "Debt Schemes"],
        "i1": ["i", "Overnight Fund", *nums(10)],
        "ii1": ["ii", "Sectoral Fund", *nums(20)],
        "sub1": ["", "Sub Total - I", *nums(30)],
        "II": ["II", "Equity Schemes"],
        "i2": ["i", "Sectoral Fund", *nums(5)],
        "sub2": ["", "Sub total II", *nums(5)],
        "totA": ["", "Total A-Open ended Schemes", *nums(35)],
        "B": ["B", "Close Ended Schemes"],
        "I_b": ["I", "Income/Debt Oriented Schemes"],
        "i3": ["i", "Fixed Term Plan", *nums(3)],
        "totB": ["", "Total B -Close ended Schemes", *nums(3)],
        "C": ["C", "Interval Schemes"],
        "i4": ["i", "Income/Debt Oriented Schemes", *nums(2)],
        "totC": ["", "Total C Interval Schemes", *nums(2)],
        "grand": ["", "Grand Total", *nums(40)],
        "fof": ["", "Fund of Funds Scheme (Domestic) **", "# 158", *nums(1)[:8]],
        "note": ["", "** Data in respect Fund of Funds Domestic is shown for information only."],
    }
    rows.update(overrides)
    return list(rows.values())


def test_parses_category_rows_only():
    df = parse_aum_rows(report())
    assert len(df) == 5
    assert df["report_month"].unique().tolist() == ["2026-09-01"]
    assert df["net_aum_inr_cr"].sum() == 40


def test_interval_schemes_have_no_class():
    df = parse_aum_rows(report()).set_index("category")
    assert df.loc["Fixed Term Plan", "scheme_class"] == "Income/Debt Oriented Schemes"
    interval = df[df["scheme_type"] == "Interval Schemes"]
    assert interval["scheme_class"].isna().all()


def test_same_category_name_under_two_classes_is_kept():
    df = parse_aum_rows(report())
    sectoral = df[df["category"] == "Sectoral Fund"]
    assert sorted(sectoral["scheme_class"]) == ["Debt Schemes", "Equity Schemes"]


def test_totals_mismatch_raises():
    with pytest.raises(AumParseError, match="Grand Total: categories do not add up"):
        parse_aum_rows(report(grand=["", "Grand Total", *nums(41)]))


def test_text_in_a_category_number_raises():
    with pytest.raises(AumParseError, match="text '# 10'"):
        parse_aum_rows(report(i1=["i", "Overnight Fund", "# 10", *nums(10)[:8]]))


def test_renamed_header_column_raises():
    header = HEADER.copy()
    header[3] = "Investor accounts as on September 30, 2026"
    with pytest.raises(AumParseError, match="num_folios"):
        parse_aum_rows(report(header=header))


def test_missing_month_raises():
    with pytest.raises(AumParseError, match="Report month"):
        parse_aum_rows(report(title=["", "Monthly Report"]))
