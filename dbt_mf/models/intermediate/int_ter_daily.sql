-- One row per (nsdl_scheme_code, ter_date, plan): the latest version of each day,
-- unpivoted so Regular and Direct are separate rows. A plan whose five components
-- are all 0 does not exist for that scheme (e.g. an ETF has no Direct plan) and is dropped.
-- A plain table, not incremental: TER is ~76k rows a month and rebuilds in seconds.

with ranked as (
    select
        *,
        row_number() over (
            partition by nsdl_scheme_code, ter_date
            order by ingested_at desc, _bronze_loaded_at desc
        ) as rn
    from {{ ref('stg_ter') }}
),

latest as (
    select * from ranked where rn = 1
),

regular as (
    select
        nsdl_scheme_code, scheme_name, scheme_type, scheme_category, ter_date,
        'Regular'                       as plan,
        regular_ber_pct                 as ber_pct,
        regular_brokerage_pct           as brokerage_pct,
        regular_transaction_cost_pct    as transaction_cost_pct,
        regular_statutory_levies_pct    as statutory_levies_pct,
        regular_total_ter_pct           as total_ter_pct,
        ingested_at
    from latest
),

direct as (
    select
        nsdl_scheme_code, scheme_name, scheme_type, scheme_category, ter_date,
        'Direct'                        as plan,
        direct_ber_pct                  as ber_pct,
        direct_brokerage_pct            as brokerage_pct,
        direct_transaction_cost_pct     as transaction_cost_pct,
        direct_statutory_levies_pct     as statutory_levies_pct,
        direct_total_ter_pct            as total_ter_pct,
        ingested_at
    from latest
),

both_plans as (
    select * from regular
    union all
    select * from direct
)

select *
from both_plans
where not (
        ber_pct = 0
    and brokerage_pct = 0
    and transaction_cost_pct = 0
    and statutory_levies_pct = 0
    and total_ter_pct = 0
)