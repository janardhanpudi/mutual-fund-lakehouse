-- Every scheme's returns next to Nifty 50's return over exactly the same dates.
--   excess return = scheme return - Nifty 50 return   (positive = beat the market)
-- Nifty's level on a date = its close on or before that date, at most 7 days older
-- (the same rule as for NAVs). Excess is NULL whenever either side is NULL.
-- Most meaningful for equity schemes; for debt and liquid funds Nifty is not a fair yardstick.

with returns as (
    select * from {{ ref('fct_scheme_returns') }}
),

nifty as (
    select price_date, close_price
    from {{ ref('int_index_daily') }}
    where ticker = '^NSEI'
),

end_dates as (
    select distinct latest_nav_date as end_date
    from returns
),

periods as (
    select * from values ('end', 0), ('1m', 1), ('3m', 3), ('6m', 6), ('1y', 12) as p(period, months)
),

points as (
    -- every date we need a Nifty level for
    select e.end_date, p.period, add_months(e.end_date, -p.months) as target_date
    from end_dates as e
    cross join periods as p
),

levels as (
    select end_date, period, close_price
    from (
        select
            pt.end_date,
            pt.period,
            n.close_price,
            row_number() over (partition by pt.end_date, pt.period order by n.price_date desc) as rn
        from points as pt
        inner join nifty as n
            on  n.price_date <= pt.target_date
            and n.price_date >= date_sub(pt.target_date, 7)
    )
    where rn = 1
),

wide as (
    select
        end_date,
        max(case when period = 'end' then close_price end) as level_end,
        max(case when period = '1m'  then close_price end) as level_1m,
        max(case when period = '3m'  then close_price end) as level_3m,
        max(case when period = '6m'  then close_price end) as level_6m,
        max(case when period = '1y'  then close_price end) as level_1y
    from levels
    group by end_date
),

benchmark as (
    select
        end_date,
        round((level_end / level_1m - 1) * 100, 2) as nifty50_return_1m_pct,
        round((level_end / level_3m - 1) * 100, 2) as nifty50_return_3m_pct,
        round((level_end / level_6m - 1) * 100, 2) as nifty50_return_6m_pct,
        round((level_end / level_1y - 1) * 100, 2) as nifty50_return_1y_pct
    from wide
)

select
    r.*,
    b.nifty50_return_1m_pct,
    b.nifty50_return_3m_pct,
    b.nifty50_return_6m_pct,
    b.nifty50_return_1y_pct,
    r.return_1m_pct - b.nifty50_return_1m_pct as excess_return_1m_pct,
    r.return_3m_pct - b.nifty50_return_3m_pct as excess_return_3m_pct,
    r.return_6m_pct - b.nifty50_return_6m_pct as excess_return_6m_pct,
    r.return_1y_pct - b.nifty50_return_1y_pct as excess_return_1y_pct
from returns as r
left join benchmark as b
    on b.end_date = r.latest_nav_date
