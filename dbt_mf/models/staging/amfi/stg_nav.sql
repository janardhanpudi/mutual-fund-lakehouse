-- One row per bronze NAV row: typed, with '' and '-' turned into NULL. No filtering or dedup here.
with bronze as (
    select * from {{ source('bronze', 'nav') }}
)

select
    scheme_code,
    scheme_name,
    nullif(trim(plan), '')                                  as plan,
    nullif(trim(`option`), '')                              as scheme_option,
    nullif(nullif(trim(isin_growth_or_payout), ''), '-')    as isin_growth_or_payout,
    nullif(nullif(trim(isin_reinvestment), ''), '-')        as isin_reinvestment,
    cast(nav as decimal(20, 6))                             as nav,
    to_date(nav_date, 'dd-MMM-yyyy')                        as nav_date,
    category_raw,
    amc,
    source                                                  as load_source,
    to_date(run_date)                                       as run_date,
    cast(ingested_at as timestamp)                          as ingested_at,
    _source_file,
    _bronze_loaded_at
from bronze
