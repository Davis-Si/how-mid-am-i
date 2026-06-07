-- Staging view over clean_results (built offline by scripts/clean_data.py).
-- Adds the canonical Ironman `cohort` + `is_official` columns and normalizes
-- gender to M/F. Cohort logic mirrors scripts/cohort_sizing.py::cohort_case_sql
-- exactly; official age bands come from a dbt var sourced from
-- config.OFFICIAL_AGE_BANDS (single source of cohort truth — do not fork).
--
-- clean_results is already finishers-only with outlier segments NULLed, so this
-- model only enriches; it does not filter.

{% set bands = var('official_age_bands') %}
{% set genders = var('cohort_genders') %}

with normalized as (

    select
        raceID,
        seriesID,
        year,
        athleteID,
        -- raw gender is 'Male' / 'Female' / NULL → normalize to M / F
        case
            when gender = 'Male'   then 'M'
            when gender = 'Female' then 'F'
        end as gender,
        division,
        is_pro,
        overall_seconds,
        swim_seconds,
        bike_seconds,
        run_seconds
    from clean_results

),

with_cohort as (

    select
        *,
        case
            when division in ('MPRO', 'FPRO') then division
            {%- for g in genders %}
            {%- for b in bands %}
            when division = '{{ g }}{{ b }}' then division
            {%- endfor %}
            {%- endfor %}
            else null
        end as cohort
    from normalized

)

select
    *,
    cohort is not null as is_official
from with_cohort
