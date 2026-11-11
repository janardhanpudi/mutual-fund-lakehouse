-- Scheme history (SCD Type 2), built from the CDC change log: one row per version of a scheme,
-- with the period it was valid. Built from the log, not a dbt snapshot, so no version is missed.
-- Clean type / class / category come from the category_map seed.

with versions as (
    -- the same version can sit in bronze twice (re-loaded files): keep one per scheme and change time
    select
        *,
        row_number() over (
            partition by scheme_code, updated_at
            order by extracted_at desc
        ) as rn
    from {{ ref('stg_scheme_master_cdc') }}
),

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
        -- the first version we saw is treated as valid from the beginning: tracking started
        -- on 7 Nov 2026, but the schemes (and their NAV history) are older than that
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
),

tidied as (
    -- remove AMFI's footnote stars and repeated spaces before cutting the heading up
    select
        *,
        regexp_replace(regexp_replace(category_raw, '\\s*\\*+', ''), '\\s+', ' ') as heading
    from history
),

keyed as (
    -- "Type(Class - Category)" -> three pieces; headings without " - " have no class
    select
        *,
        trim(regexp_extract(heading, '^([^(]+)\\(', 1))                          as scheme_type_raw,
        case
            when heading like '% - %'
                then trim(regexp_extract(heading, '^[^(]+\\((.*?) - (.*)\\)$', 1))
            else '(none)'
        end                                                                      as class_raw,
        case
            when heading like '% - %'
                then trim(regexp_extract(heading, '^[^(]+\\((.*?) - (.*)\\)$', 2))
            else trim(regexp_extract(heading, '^[^(]+\\((.*)\\)$', 1))
        end                                                                      as category_raw_name
    from tidied
)

select
    k.scheme_code,
    k.scheme_name,
    k.plan,
    k.scheme_option,
    k.isin_growth_or_payout,
    k.isin_reinvestment,
    k.amc,
    case k.scheme_type_raw
        when 'Open Ended Schemes'    then 'Open Ended'
        when 'Close Ended Schemes'   then 'Close Ended'
        when 'Interval Fund Schemes' then 'Interval'
    end                                              as scheme_type,
    nullif(m.class_std, '(none)')                    as scheme_class,
    m.category_std                                   as category,
    m.mapping                                        as category_mapping,
    k.category_raw,
    k.valid_from,
    k.valid_to,
    k.valid_to is null                               as is_current
from keyed as k
left join {{ ref('category_map') }} as m
    on  k.scheme_type_raw   = m.scheme_type
    and k.class_raw         = m.class_raw
    and k.category_raw_name = m.category_raw_name
