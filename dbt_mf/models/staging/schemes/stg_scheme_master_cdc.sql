-- Typed scheme changes from Neon. Same NULL rules as stg_nav, so attributes compare equal across both.
with bronze as (
    select * from {{ source('bronze', 'scheme_master_cdc') }}
)

select
    scheme_code,
    scheme_name,
    nullif(trim(plan), '')                                  as plan,
    nullif(trim(`option`), '')                              as scheme_option,
    nullif(nullif(trim(isin_growth_or_payout), ''), '-')    as isin_growth_or_payout,
    nullif(nullif(trim(isin_reinvestment), ''), '-')        as isin_reinvestment,
    category_raw,
    amc,
    cast(created_at as timestamp)                           as created_at,
    cast(updated_at as timestamp)                           as updated_at,
    cast(extracted_at as timestamp)                         as extracted_at,
    _source_file,
    _bronze_loaded_at
from bronze
