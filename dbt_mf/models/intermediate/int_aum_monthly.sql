
with ranked as (
    select
        *,
        row_number() over (
            partition by report_month, scheme_type, scheme_class, category
            order by ingested_at desc, _bronze_loaded_at desc
        ) as rn
    from {{ ref('stg_aum') }}
)

select
    report_month,
    scheme_type,
    scheme_class,
    category,
    num_schemes,
    num_folios,
    funds_mobilized_inr_cr,
    redemption_inr_cr,
    net_flow_inr_cr,
    net_aum_inr_cr,
    avg_net_aum_inr_cr,
    segregated_portfolios,
    segregated_net_aum_inr_cr,
    run_date,
    ingested_at
from ranked
where rn = 1