select ticker, price_date, count(*) as copies
from {{ ref('int_index_daily') }}
group by ticker, price_date
having count(*) > 1
