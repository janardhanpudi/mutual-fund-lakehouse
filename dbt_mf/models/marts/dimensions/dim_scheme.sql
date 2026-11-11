-- Scheme history (SCD Type 2), built from the CDC change log: one row per version of a scheme,
-- with the period it was valid. Built from the log, not a dbt snapshot, so no version is missed.

with versions as (
    -- the same version can sit in bronze twice (re-loaded files): keep one per scheme and change time
    select
        *,
        row_number() over (
            partition by scheme_code, updated_at
            order by extracted_at desc
        ) as rn
    from {{ ref('stg_scheme_master_cdc') }}
),                                                   -- comma, not a second "with"

history as (
    select
        scheme_code,
        scheme_name,
        plan,
        scheme_option,
        isin_growth_or_payout,
        isin_reinvestment,
        category_raw,
        amc,
        case
            when lag(updated_at) over (partition by scheme_code order by updated_at) is null
                then timestamp '1900-01-01 00:00:00'
            else updated_at
        end                                          as valid_from,
        lead(updated_at) over (
            partition by scheme_code
            order by updated_at
        )                                            as valid_to
    from versions
    where rn = 1
)

select
    *,
    valid_to is null                                 as is_current
from history