-- Drawdown is a fall, so it is between -100% and 0%. Volatility cannot be negative.
select scheme_code, max_drawdown_1y_pct, volatility_1y_pct
from {{ ref('fct_scheme_risk') }}
where max_drawdown_1y_pct < -100
   or max_drawdown_1y_pct > 0
   or volatility_1y_pct < 0
