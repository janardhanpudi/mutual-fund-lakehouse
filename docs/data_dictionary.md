# Data Dictionary — Mutual Fund Lakehouse

Explored on Day 2 (1–4 Nov 2026) in `notebooks/01_explore_sources.ipynb`.
Raw files are kept unchanged in `data/raw/` (git-ignored). All cleanup happens in silver (dbt), never in bronze.

## Sources at a glance

| Source | Access | Format | Frequency | Grain | Key |
|---|---|---|---|---|---|
| AMFI daily NAV | `GET https://www.amfiindia.com/spages/NAVAll.txt` | `;`-separated text with heading lines | Daily | One row per scheme variant (latest NAV only) | `scheme_code` (within one file); `(scheme_code, nav_date)` across days |
| AMFI NAV history | `GET https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?tp=&frmdt=&todt=` | `;`-separated text with heading lines | On demand, max 90 days per request | One row per scheme variant per date | `(scheme_code, nav_date)` |
| Benchmarks | `yfinance` (`^NSEI` Nifty 50, `^BSESN` Sensex) | DataFrame | Daily (trading days) | One row per index per trading date | `(ticker, date)` |
| AMFI monthly AUM | AMFI Monthly page, Excel per month (e.g. `amsep2026repo.xls`) | Legacy `.xls` (CDF V2, code page 1252) | Monthly | One row per fund category | `(scheme_type, scheme_class, category, report_month)` |
| AMFI TER | `GET https://www.amfiindia.com/api/populate-te-rdata-revised?MF_ID=All&Month=MM-YYYY&strCat=-1&strType=-1&excel=true` | `.xlsx` | Monthly file with daily rows | One row per base scheme per date (Regular and Direct side by side) | `(nsdl_scheme_code, ter_date)` |

---

## 1. AMFI daily NAV (`NAVAll.txt`)

**Snapshot explored:** downloaded 2026-11-01 — 18,230 lines, 14,441 data rows, newest NAV date 2026-11-01.

| Raw column | Target column | Type | Notes |
|---|---|---|---|
| Scheme Code | `scheme_code` | string | Unique within the file (14,441 rows, 14,441 codes) |
| ISIN Div Payout/ ISIN Growth | `isin_growth_or_payout` | string, nullable | `-` means missing |
| ISIN Div Reinvestment | `isin_reinvestment` | string, nullable | `-` means missing |
| Scheme Name | `scheme_name` | string | **Base** name; not unique (5,947 rows share name + plan + option) |
| Plan | `plan` | string, nullable | Blank for 5,709 rows (91% of them stale) → `Not applicable` |
| Option | `option` | string, nullable | Inconsistent labels: `Growth`, `Growth Option`, `GROWTH`, several IDCW forms |
| Net Asset Value | `nav` | decimal | No text values seen. **0 is legitimate** (241 rows on 1 Nov: written-off segregated portfolios) — kept with a warning, excluded from returns in silver; text, blank or negative stops the run |
| Date | `nav_date` | date | Format `DD-Mon-YYYY`; **not** the download date |
| (heading line) | `category_raw` | string | Carried down from `Open/Close Ended/Interval Fund Schemes(...)` lines |
| (heading line) | `amc` | string | Carried down from fund-house lines |

**Quirks and rules**
- Header row has 8 columns (newer layout; older tutorials show 6). Map columns **by header name**, never by position.
- Blank lines contain one space; test with `strip()`.
- Fund-house headings vary (`ASK MUTUAL FUND`, `IL&FS Mutual Fund (IDF)`): match case-insensitively, allow suffixes.
- **A new category heading does not always repeat the fund house:** 17 Franklin rows (line 965 of the 1 Nov file) follow a category heading directly. The fund house carries over from the previous block.
- The file uses Windows line endings (`\r\n`); `splitlines()` handles them.
- 56 distinct fund-house headings on 1 Nov (more than the ~45–50 active houses; likely merged or closed houses with stale rows — check in silver).
- Category headings mix curly and straight apostrophes and repeated spaces; normalize, never hard-code.
- 104 raw categories using both old and new SEBI naming (`Debt Scheme - Liquid Fund` vs `Income/Debt Oriented Schemes - Liquid Fund`) → mapped by a dbt seed.
- **Stale rows:** 8,802 rows 0–3 days old, 21 at 4–30 days, 230 at 31–365 days, 5,388 over 1 year. Active = latest NAV within 30 days of the file's newest date (8,823 variants). Bronze keeps all rows.
- **Weekend NAVs:** 813 rows dated Sat 31-Oct and 712 dated Sun 01-Nov — liquid and overnight funds, but also index, sectoral and ETF schemes. No hard-coded weekend rule.
- The file holds only each scheme's **latest** NAV: a missed day cannot be recovered from it (use NAV history).

## 2. AMFI NAV history

**Test explored:** 24–30 Oct 2026, `tp=1` — 200 OK, about 5.9 MB, 44,395 rows, 0 duplicate `(scheme_code, nav_date)`.

Same fields as the daily file, but a different layout:

| Aspect | Daily file | History file |
|---|---|---|
| Column order | Code, ISIN 1, ISIN 2, Scheme Name, Plan, Option, NAV, Date | Code, **NAV Name**, Plan, Option, ISIN 1, ISIN 2, NAV, Date |
| ISIN 1 header | `ISIN Div Payout/ ISIN Growth` | `ISIN Div Payout/ISIN Growth` |
| Blank lines | `' '` | `''` |
| Category heading | `Schemes(...)` | `Schemes ( ... )` |
| Missing ISIN | `-` | empty |
| Name | Base name | Variant name (`...-Direct Growth`) |

**Reconciliation on 30-Oct-2026 (history fetched 1 Nov):** 7,130 rows in both with **0 NAV mismatches** and 0 category mismatches; 1,469 history-only (daily file had a later date for those schemes); 108 daily-only (`tp=1` returns open-ended schemes only: 104 close-ended + 4 interval).

**Same comparison, history re-fetched 4 Nov:** history grew from 44,395 to 44,433 rows (30-Oct: 8,599 → 8,637), and **8 of 7,130 NAVs differ** from the 1 Nov daily file (e.g. scheme 117446: 2790.0283 vs 2790.3836).
- **Late NAVs:** 38 schemes whose latest NAV in the 1 Nov daily file was 29-Oct now have a 30-Oct NAV in history.
- **Revised NAVs:** AMFI data for a past date can change after publication.

**Rules**
- Used for **backfill and gap-filling**, max 90 days per request; request every scheme type: `tp=1` open-ended (8,637 rows on 30-Oct), `tp=2` close-ended (160), `tp=3` interval (4). The meaning of `tp` lives on AMFI's server and was found by testing.
- Every daily run also re-fetches a **trailing window** (e.g. last 7 days) from history and merges on `(scheme_code, nav_date)` with **latest value wins**, so late and revised NAVs are picked up. Keep `ingested_at` so revisions can be traced.
- Supplies only `scheme_code`, `nav_date`, `nav` to facts. Scheme attributes come **only** from the daily file, so SCD2 never records fake changes from switching sources.
- About 300 MB of raw text per year: store compressed, convert to Parquet.

## 3. Benchmarks (yfinance)

**Explored:** 2024-10-01 to 2026-10-30 — Nifty 515 closes (0 missing), Sensex 514 (1 missing).

| Field | Target column | Type | Notes |
|---|---|---|---|
| Date (index) | `price_date` | date | No time zone |
| Ticker | `index_code` | string | `^NSEI`, `^BSESN` |
| Close | `close` | decimal(12,2) | Round float noise to 2 decimals |
| Open, High, Low | `open`, `high`, `low` | decimal(12,2) | Kept for completeness |
| Adj Close | — | dropped | Equal to Close for indices |
| Volume | — | dropped | Not meaningful for indices on Yahoo |

**Quirks and rules**
- Weekend trading days exist (2025-02-01, a Saturday Budget session, has Nifty but no Sensex). Build the trading calendar from Nifty's actual dates; test for Yahoo gaps.
- Unofficial API: can rate-limit or return empty data → retries with backoff, failures visible.
- yfinance raises `Pandas4Warning` under pandas 3.1; keep `uv.lock` committed.

## 4. AMFI monthly AUM report

**Explored:** September 2026 report (`amsep2026repo.xls`), sheet `MCR_MonthlyReport` (110 × 11). Sheet `NSR` (new schemes launched) is not used.

| Column | Target column | Type | Unit |
|---|---|---|---|
| Sr (code) | used for hierarchy | — | `A/B/C`, `I…VIII`, `i, ii…` |
| Scheme Name | `category` | string | Strip `**`, `##`, `#` markers |
| No. of Schemes | `num_schemes` | integer | |
| No. of Folios | `num_folios` | integer | |
| Funds Mobilized | `funds_mobilized_inr_cr` | decimal | INR crore |
| Repurchase/Redemption | `redemption_inr_cr` | decimal | INR crore |
| Net Inflow/Outflow | `net_flow_inr_cr` | decimal | INR crore |
| Net AUM | `net_aum_inr_cr` | decimal | INR crore, month end |
| Average Net AUM | `avg_net_aum_inr_cr` | decimal | INR crore, month average |
| No. of segregated portfolios | `segregated_portfolios` | integer | |
| Net AUM in segregated portfolio | `segregated_net_aum_inr_cr` | decimal | INR crore |
| (title row) | `report_month` | date | Parsed from the title, not the filename |
| (hierarchy) | `scheme_type`, `scheme_class` | string | Class is null for interval schemes |

**Rules**
- Read with `xlrd` (openpyxl cannot read legacy `.xls`). Header at row 2 (xlrd index).
- Keep a row only if its code is a lowercase Roman numeral; subtotal labels are inconsistent.
- A new type resets the class. Match classes with `[IVX]+` so type `C` is not read as a numeral.
- Key includes type and class: `Sectoral Fund` appears under Debt and Equity.
- Header text contains the month → match columns by pattern.
- Any text in a numeric cell of a kept row stops the run (`# 158` appeared in the dropped FoF row).
- The `Fund of Funds Scheme (Domestic)` row is excluded: AMFI's footnote says it is already counted in the underlying schemes.
- Category-level data: joins to schemes through the category seed, not `scheme_code`.

**Validation:** 61 leaf rows (56 open-ended, 4 close-ended, 1 interval), 0 duplicate keys, 0 NaN cells; leaf sums equal Grand Total and Totals A, B, C exactly.

## 5. AMFI TER (total expense ratio)

**Explored:** October 2026 — one request, about 25 s, 4.5 MB; 64,555 rows = 64,542 data rows + 13 disclaimer/blank rows.

| Raw column | Target column | Type | Notes |
|---|---|---|---|
| NSDL Scheme Code | `nsdl_scheme_code` | string | NSDL code, **not** AMFI `scheme_code`; clean to `[A-Z0-9/]` |
| Scheme Name | `scheme_name` | string | Base name; join key to NAV (below) |
| Scheme Type | `scheme_type` | string | e.g. `Open Ended` |
| Scheme Category | `scheme_category` | string | Clean names, e.g. `Hybrid Schemes - Balanced Hybrid Fund` |
| TER Date | `ter_date` | date | Daily; keep the date part only |
| Regular Plan - Base Expense Ratio (BER) (%) | `ber_pct` (plan = Regular) | decimal | Annualized |
| Regular Plan - Brokerage cost (%) | `brokerage_pct` | decimal | Cumulative average over the reference period |
| Regular Plan - Transaction Cost … (%) | `transaction_cost_pct` | decimal | Cumulative average over the reference period |
| Regular Plan - Statutory Levies (including GST) (%) | `statutory_levies_pct` | decimal | |
| Regular Plan - Total TER (%) | `total_ter_pct` | decimal | = sum of the four parts |
| Direct Plan - … (same five) | same, plan = Direct | decimal | Unpivoted to one row per plan in silver |

**Quirks and rules**
- `excel=true` returns the whole month in one request; the paginated JSON is capped at 100 rows per page (646 requests).
- Drop rows with no `TER Date`: the file ends with 1 blank row and 12 disclaimer lines.
- **Dirty key:** `HDFC/O/O/OET/21/12/0093?` (literal `?`, 18 rows) and `HDFC/O/O/OET/21/12/0093` (13 rows) are one ETF on disjoint dates; cleaning the code merges them into 31 days.
- 2,176 distinct codes after cleaning; (code, date) is unique.
- Not every scheme has every day (1,892 have all 31; 201 have exactly 20, on differing dates; cause unknown). Store as valid-from / valid-to periods, carrying the last value forward.
- Components sum to the total for every row, both plans (0 mismatches) → dbt test.
- **Late rows:** the October total grew from 64,542 (1 Nov) to 64,544 (4 Nov). The monthly job re-fetches the previous month and merges on `(nsdl_scheme_code, ter_date)`.
- **Implausible values:** latest-value maximums are 45.44% (Direct) and 16.38% (Regular), far above SEBI's TER limits. dbt test: flag total TER outside a plausible range (e.g. 0–3%) for review.
- The disclaimer contains a template error (`GST rate is XX%`): official files are not perfect.

**Join to NAV schemes**
- Key = `scheme_name` lowercased with everything except letters and digits removed.
- TER → NAV: 2,176 of 2,176 matched; 0 collisions within TER. Collisions within NAV (4) are one fund house's variant names padded with spaces — safe to merge.
- NAV schemes with no TER (14): allow-list of 13 — segregated portfolios (5) and legacy plans named as schemes (8). `Nippon India CRISIL-IBX FAR Gilt ETF` stays flagged (cause unknown).
- dbt test: any active scheme with no TER and not on the allow-list fails.

---

## Landing layout (NAV extractor, Day 3)

`python -m mf_lakehouse.extract.nav` (daily) or `--start YYYY-MM-DD --end YYYY-MM-DD` (backfill) writes:

```
data/landing/nav/source=daily/run_date=<date>/nav.parquet
data/landing/nav/source=history/run_date=<date>/nav.parquet        (last 7 days)
data/landing/nav/backfill=<start>_<end>/source=history/run_date=<date>/nav.parquet
```

- Folders are named by **run date** (when fetched); each row keeps its own `nav_date`. Naming folders by NAV date would rewrite hundreds of old folders daily because of stale rows.
- Added columns: `source` (`daily`/`history`), `run_date`, `ingested_at` (UTC).
- Rerunning the same day overwrites the same file (idempotent). Silver resolves daily vs history and revisions by `(scheme_code, nav_date)`, latest `ingested_at` wins.

## Cross-source decisions

| Decision | Reason |
|---|---|
| Daily NAV file is the only source of scheme attributes | Mixing sources would create fake SCD2 versions |
| NAV history fills gaps and backfills | The daily file holds only the latest NAV per scheme |
| One dbt seed maps raw categories | Serves NAV (104 categories) and AUM (61) |
| Bronze keeps raw values | Cleanup belongs in silver |
| Parsers fail loudly | Unknown columns, wrong field counts, text in numeric cells, page-size changes stop the run |
| No fund manager field | No central source; dropped from scope (agreed 1 Nov 2026) |
