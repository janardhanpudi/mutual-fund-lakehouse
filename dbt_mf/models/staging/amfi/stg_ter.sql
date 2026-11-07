-- Typed TER rows, still one row per scheme per day with Regular and Direct side by side.
-- Unpivoting to one row per plan, and treating an ETF's Direct 0 as missing, happen in intermediate.
with bronze as (
    select * from {{ source('bronze', 'ter') }}
)

select
    nsdl_scheme_code,
    scheme_name,
    scheme_type,
    scheme_category,
    to_date(ter_date)                                       as ter_date,
    cast(regular_ber_pct as decimal(9, 4))                  as regular_ber_pct,
    cast(regular_brokerage_pct as decimal(9, 4))            as regular_brokerage_pct,
    cast(regular_transaction_cost_pct as decimal(9, 4))     as regular_transaction_cost_pct,
    cast(regular_statutory_levies_pct as decimal(9, 4))     as regular_statutory_levies_pct,
    cast(regular_total_ter_pct as decimal(9, 4))            as regular_total_ter_pct,
    cast(direct_ber_pct as decimal(9, 4))                   as direct_ber_pct,
    cast(direct_brokerage_pct as decimal(9, 4))             as direct_brokerage_pct,
    cast(direct_transaction_cost_pct as decimal(9, 4))      as direct_transaction_cost_pct,
    cast(direct_statutory_levies_pct as decimal(9, 4))      as direct_statutory_levies_pct,
    cast(direct_total_ter_pct as decimal(9, 4))             as direct_total_ter_pct,
    ter_month,
    to_date(run_date)                                       as run_date,
    cast(ingested_at as timestamp)                          as ingested_at,
    _source_file,
    _bronze_loaded_at
from bronze
