-- Each fund's rank inside its category, by 1-year return.
--   * Growth options only (IDCW payouts understate returns)
--   * ranked separately for each plan (Direct and Regular have different costs)
--   * funds with a unit-split break are left out (their 1y return is NULL)
--   * rank 1 = best fund in its group
--   * top_pct = rank as a percent of the group: 25 or lower = top quartile

with eligible as (
    select
        scheme_code,
        scheme_name,
        amc,
        category,
        plan,
        option_type,
        as_of_date,
        return_1y_pct
    from {{ ref('fct_scheme_returns') }}
    where option_type = 'Growth'
      and category is not null
      and plan is not null
      and return_1y_pct is not null
      and not has_nav_break
),

ranked as (
    select
        *,
        count(*) over (partition by category, plan)                       as category_size,
        rank() over (partition by category, plan order by return_1y_pct desc) as category_rank
    from eligible
)

select
    *,
    round(category_rank * 100.0 / category_size, 1) as top_pct
from ranked
