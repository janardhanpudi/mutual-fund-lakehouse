-- Rank must be between 1 and the group size, and top_pct between 0 and 100.
select scheme_code, category, plan, category_rank, category_size, top_pct
from {{ ref('fct_category_rankings') }}
where category_rank < 1
   or category_rank > category_size
   or top_pct <= 0
   or top_pct > 100
