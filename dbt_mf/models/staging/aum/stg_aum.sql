-- Typed AUM rows, one per category per report month. Money is INR crore.
with bronze as (
    select * from {{ source('bronze', 'aum') }}
)

select
    to_date(report_month)                                   as report_month,
    scheme_type,
    scheme_class,
    category,
    cast(num_schemes as int)                                as num_schemes,
    cast(num_folios as bigint)                              as num_folios,
    cast(funds_mobilized_inr_cr as decimal(20, 4))          as funds_mobilized_inr_cr,
    cast(redemption_inr_cr as decimal(20, 4))               as redemption_inr_cr,
    cast(net_flow_inr_cr as decimal(20, 4))                 as net_flow_inr_cr,
    cast(net_aum_inr_cr as decimal(20, 4))                  as net_aum_inr_cr,
    cast(avg_net_aum_inr_cr as decimal(20, 4))              as avg_net_aum_inr_cr,
    cast(segregated_portfolios as int)                      as segregated_portfolios,
    cast(segregated_net_aum_inr_cr as decimal(20, 4))       as segregated_net_aum_inr_cr,
    to_date(run_date)                                       as run_date,
    cast(ingested_at as timestamp)                          as ingested_at,
    _source_file,
    _bronze_loaded_at
from bronze
