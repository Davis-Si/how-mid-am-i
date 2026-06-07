-- Segment splits, when present, must lie within the cleaner's documented
-- physiological bounds (scripts/clean_data.py constants):
--   swim 30min..2h20 = 1800..8400 s
--   bike 3h30..10h   = 12600..36000 s
--   run  2h15..8h20  = 8100..30000 s
-- Outlier segments were NULLed upstream, so a non-null value out of range = bug.
-- Returns offending rows; the test passes when zero are returned.
select raceID, athleteID, 'swim' as segment, swim_seconds as seconds
from {{ ref('fct_results') }}
where swim_seconds is not null and swim_seconds not between 1800 and 8400

union all

select raceID, athleteID, 'bike' as segment, bike_seconds as seconds
from {{ ref('fct_results') }}
where bike_seconds is not null and bike_seconds not between 12600 and 36000

union all

select raceID, athleteID, 'run' as segment, run_seconds as seconds
from {{ ref('fct_results') }}
where run_seconds is not null and run_seconds not between 8100 and 30000
