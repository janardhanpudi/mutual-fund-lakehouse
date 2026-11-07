-- Typed index prices; Yahoo's float noise rounded to 2 decimals.
with bronze as (
    select * from {{ source('bronze', 'index_prices') }}
)

select
    ticker,
    case ticker
        when '^NSEI'  then 'NIFTY 50'
        when '^BSESN' then 'SENSEX'
    end                                                     as index_name,
    to_date(price_date)                                     as price_date,
    cast(round(open, 2) as decimal(12, 2))                  as open_price,
    cast(round(high, 2) as decimal(12, 2))                  as high_price,
    cast(round(low, 2) as decimal(12, 2))                   as low_price,
    cast(round(close, 2) as decimal(12, 2))                 as close_price,
    to_date(run_date)                                       as run_date,
    cast(ingested_at as timestamp)                          as ingested_at,
    _source_file,
    _bronze_loaded_at
from bronze
