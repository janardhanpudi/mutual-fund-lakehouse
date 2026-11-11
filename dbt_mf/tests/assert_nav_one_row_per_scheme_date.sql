-- int_nav_clean must have exactly one row per (scheme_code, nav_date).
-- Returns the duplicated pairs; the test passes when nothing comes back.
select scheme_code, nav_date, count(*) as copies
from {{ ref('int_nav_clean') }}
group by scheme_code, nav_date
having count(*) > 1
