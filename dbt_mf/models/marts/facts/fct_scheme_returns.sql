-- Point-to-point returns for every active scheme, as of its latest NAV.
--   return = (latest NAV / NAV one period earlier - 1) * 100
-- Rules:
--   * active  = latest priced NAV is within 30 days of the latest trading day
--   * "NAV one period earlier" = the latest NAV on or before that date, at most 7 days older
--   * zero NAVs (written-off segregated portfolios) are ignored; no earlier NAV -> return is NULL
--   * NAV breaks: AMFI NAVs are not adjusted for unit splits (e.g. an ETF splitting 10-for-1
--     shows a 90% one-day "fall"). A step of more than 40% between two consecutive NAVs is
--     treated as a break; any return whose period contains a break is NULL, and
--     has_nav_break says why. Flagged, not adjusted: the split ratio is not known for certain.
-- Note: IDCW options pay money out, which lowers their NAV, so their returns understate
-- performance. Growth options are the ones to compare.

with as_of as (
    select max(trade_date) as as_of_date
    from {{ ref('int_trading_calendar') }}
),

navs as (
    -- priced NAVs up to the latest trading day (liquid funds publish weekend NAVs in advance)
    select n.scheme_code, n.nav_date, n.nav
    from {{ ref('int_nav_clean') }} as n
    cross join as_of as a
    where n.is_priced
      and n.nav_date <= a.as_of_date
),

latest as (
    select scheme_code, nav_date, nav
    from (
        select *, row_number() over (partition by scheme_code order by nav_date desc) as rn
        from navs
    )
    where rn = 1
),

active as (
    select l.scheme_code, l.nav_date as latest_nav_date, l.nav as latest_nav, a.as_of_date
    from latest as l
    cross join as_of as a
    where l.nav_date >= date_sub(a.as_of_date, 30)
),

breaks as (
    -- the latest date on which a scheme's NAV jumped by more than 40% in one step
    select scheme_code, max(nav_date) as last_break_date
    from (
        select
            scheme_code,
            nav_date,
            nav,
            lag(nav) over (partition by scheme_code order by nav_date) as prev_nav
        from navs
    )
    where nav / prev_nav < 0.6
       or nav / prev_nav > 1.67
    group by scheme_code
),

periods as (
    select * from values ('1m', 1), ('3m', 3), ('6m', 6), ('1y', 12) as p(period, months)
),

targets as (
    -- the date one period before each scheme's latest NAV
    select s.scheme_code, p.period, add_months(s.latest_nav_date, -p.months) as target_date
    from active as s
    cross join periods as p
),

past as (
    select scheme_code, period, target_date, past_nav
    from (
        select
            t.scheme_code,
            t.period,
            t.target_date,
            n.nav as past_nav,
            row_number() over (partition by t.scheme_code, t.period order by n.nav_date desc) as rn
        from targets as t
        inner join navs as n
            on  n.scheme_code = t.scheme_code
            and n.nav_date   <= t.target_date
            and n.nav_date   >= date_sub(t.target_date, 7)
    )
    where rn = 1
),

returns as (
    -- a return is kept only if no NAV break lies between its start date and the latest NAV
    select
        a.scheme_code,
        max(case when p.period = '1m' then round((a.latest_nav / p.past_nav - 1) * 100, 2) end) as return_1m_pct,
        max(case when p.period = '3m' then round((a.latest_nav / p.past_nav - 1) * 100, 2) end) as return_3m_pct,
        max(case when p.period = '6m' then round((a.latest_nav / p.past_nav - 1) * 100, 2) end) as return_6m_pct,
        max(case when p.period = '1y' then round((a.latest_nav / p.past_nav - 1) * 100, 2) end) as return_1y_pct
    from active as a
    left join breaks as b
        on b.scheme_code = a.scheme_code
    left join past as p
        on  p.scheme_code = a.scheme_code
        and (b.last_break_date is null or b.last_break_date <= p.target_date)
    group by a.scheme_code
)

select
    a.scheme_code,
    d.scheme_name,
    d.amc,
    d.plan,
    d.scheme_option,
    d.scheme_type,
    d.scheme_class,
    d.category,
    d.category_mapping,
    a.as_of_date,
    a.latest_nav_date,
    a.latest_nav,
    r.return_1m_pct,
    r.return_3m_pct,
    r.return_6m_pct,
    r.return_1y_pct,
    coalesce(b.last_break_date > add_months(a.latest_nav_date, -12), false) as has_nav_break,
    b.last_break_date                                                      as last_nav_break_date
from active as a
inner join returns as r
    on r.scheme_code = a.scheme_code
left join breaks as b
    on b.scheme_code = a.scheme_code
left join {{ ref('dim_scheme') }} as d
    on  d.scheme_code = a.scheme_code
    and d.is_current
