{{ config(
    materialized='incremental',
    unique_key=['scheme_code', 'nav_date'],
    incremental_strategy='merge'
) }}

-- One row per (scheme_code, nav_date): the version with the latest ingested_at wins.
-- Incremental: each run re-decides only the (scheme, date) pairs that received new bronze rows,
-- using ALL their versions, so a re-loaded old file can never beat a newer revision.

with new_rows as (
    select scheme_code, nav_date
    from {{ ref('stg_nav') }}
    {% if is_incremental() %}
    where _bronze_loaded_at > (select max(_bronze_loaded_at) from {{ this }})
    {% endif %}
),

affected as (
    select distinct scheme_code, nav_date
    from new_rows
),

candidates as (
    select s.*
    from {{ ref('stg_nav') }} as s
    inner join affected as a
        on  s.scheme_code = a.scheme_code
        and s.nav_date    = a.nav_date
),

ranked as (
    select
        *,
        row_number() over (
            partition by scheme_code, nav_date
            order by ingested_at desc, _bronze_loaded_at desc
        ) as rn
    from candidates
)

select
    scheme_code,
    scheme_name,
    plan,
    scheme_option,
    isin_growth_or_payout,
    isin_reinvestment,
    nav,
    nav_date,
    category_raw,
    amc,
    load_source,
    ingested_at,
    _bronze_loaded_at,
    nav > 0 as is_priced          -- false for written-off segregated portfolios (NAV 0)
from ranked
where rn = 1