-- The (raceID, athleteID) grain must be unique among rows with a known athlete.
-- (Some source rows have NULL athleteID — those are exempt from the grain.)
select raceID, athleteID
from {{ ref('fct_results') }}
where athleteID is not null
group by raceID, athleteID
having count(*) > 1
