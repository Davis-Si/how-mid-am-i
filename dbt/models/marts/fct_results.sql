-- The analysis grain: one row per (raceID, athleteID) finisher.
-- This is the table the percentile engine reads. Materialized as a table so the
-- read path is fast and stable. Segment seconds may be NULL (outliers were
-- NULLed upstream); the percentile queries filter per-discipline.

select
    raceID,
    athleteID,
    year,
    cohort,
    gender,
    is_official,
    is_pro,
    overall_seconds,
    swim_seconds,
    bike_seconds,
    run_seconds
from {{ ref('stg_results') }}
