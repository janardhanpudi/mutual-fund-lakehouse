-- A return below -100% is impossible (it would mean a negative NAV);
-- a 1-year return above +1000% is almost certainly a missed unit split.
select scheme_code, return_1y_pct
from {{ ref('fct_scheme_returns') }}
where return_1y_pct < -100
   or return_1y_pct > 1000
