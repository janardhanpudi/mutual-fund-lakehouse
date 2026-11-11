-- Risk over the last 12 months, for each active scheme.
--   volatility_1y_pct   = how much daily returns swing, annualised (higher = bumpier)
--   max_drawdown_1y_pct = largest fall from a peak to a later low (a negative number)
-- Rules:
--   * window = priced NAVs in the 12 months up to the scheme's latest NAV date
--   * schemes with a unit-split break in that window are left out (has_nav_break)
--   * annualised with observations per year, not trading days: liquid funds publish weekend NAVs
--   * needs at least 100 daily returns, otherwise the numbers are NULL

with returns as (
    select scheme_code, latest_nav_date, has_nav_break
    from {{ ref('fct_scheme_returns') }}
),

window_navs as (
    select
        n.scheme_code,
        n.nav_date,
        n.nav,
        r.latest_nav_date
    from {{ ref('int_nav_clean') }} as n
    inner join returns as r
        on r.scheme_code = n.scheme_code
    where n.is_priced
      and not r.has_nav_break
      and n.nav_date <= r.latest_nav_date
      and n.nav_date >  add_months(r.latest_nav_date, -12)
),

with_moves as (
    select
        scheme_code,
        nav_date,
        nav,
        latest_nav_date,
        nav / lag(nav) over (partition by scheme_code order by nav_date) - 1  as daily_return,
        max(nav) over (
            partition by scheme_code order by nav_date
            rows between unbounded preceding and current row
        ) as running_peak
    from window_navs
),

per_scheme as (
    select
        scheme_code,
        max(latest_nav_date)                              as latest_nav_date,
        count(daily_return)                               as daily_returns,
        stddev_samp(daily_return)                         as daily_stddev,
        min(nav / running_peak - 1)                       as max_drawdown,
        datediff(max(nav_date), min(nav_date)) / 365.25   as span_years
    from with_moves
    group by scheme_code
)

select
    scheme_code,
    latest_nav_date,
    daily_returns,
    case when daily_returns >= 100
         then round(daily_stddev * sqrt(daily_returns / span_years) * 100, 2)
    end                                  as volatility_1y_pct,
    case when daily_returns >= 100
         then round(max_drawdown * 100, 2)
    end                                  as max_drawdown_1y_pct
from per_scheme
