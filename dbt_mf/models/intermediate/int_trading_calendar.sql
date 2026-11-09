-- One row per trading day: a day on which Nifty or Sensex has a price (either one,
-- so a Yahoo gap in one index cannot remove a real trading day). NAV dates are not used:
-- liquid and overnight funds publish NAVs on weekends too.

with trade_days as (
    select distinct price_date as trade_date
    from {{ ref('int_index_daily') }}
),
trade_day_rankings as (
    select
        trade_date,
        lag(trade_date) over (order by trade_date) as prev_trade_date,
        row_number() over (order by trade_date) as trading_day_number,
        max(trade_date) over (
            partition by year(trade_date), month(trade_date)
        ) as max_trade_date_in_month
    from trade_days
)

select
    trade_date,
    prev_trade_date,
    trading_day_number,
    trade_date = max_trade_date_in_month
    and trade_date < trunc(current_date(), 'MM') as is_month_end
from trade_day_rankings