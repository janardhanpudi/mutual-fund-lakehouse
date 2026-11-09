-- One row per (ticker, price_date): the latest version wins.

with ranked as (
    select
        *,
        row_number() over (
            partition by ticker, price_date
            order by ingested_at desc, _bronze_loaded_at desc
        ) as rn
    from {{ ref('stg_index_prices') }}
)

select
    ticker,
    index_name,
    price_date,
    open_price,
    high_price,
    low_price,
    close_price,
    ingested_at
from ranked
where rn = 1