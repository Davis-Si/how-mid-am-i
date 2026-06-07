-- Mirrors the cleaner's overall bound (7h..19h = 25200..68400 s).
-- Returns offending rows; dbt test passes when zero are returned.
select overall_seconds
from {{ ref('fct_results') }}
where overall_seconds not between 25200 and 68400
