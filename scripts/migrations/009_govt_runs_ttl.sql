-- 009_govt_runs_ttl.sql
--
-- govt_collection_runs grows by ~47 rows per nightly collection plus any
-- ad-hoc runs (defect D-20). Without a TTL the table becomes the largest
-- audit table in the system within a year.
--
-- This migration installs a daily prune job. Use `pg_cron` if available,
-- otherwise the scheduler triggers `tasks.prune_govt_runs` (a thin wrapper
-- around the same DELETE) — see backend/tasks/govt_doctor_task.py for the
-- application-side trigger.

-- 1. Index to make the time-range DELETE cheap.
CREATE INDEX IF NOT EXISTS govt_collection_runs_started_at_idx
    ON govt_collection_runs (started_at);

-- 2. Optional: enable pg_cron-based prune. Wrapped in a DO block so the
-- migration succeeds on instances without pg_cron (Supabase managed has it
-- by default; bare-metal Postgres usually doesn't).
DO $$
BEGIN
    PERFORM 1
    FROM pg_extension
    WHERE extname = 'pg_cron';

    IF FOUND THEN
        EXECUTE $cron$
            SELECT cron.schedule(
                'govt-collection-runs-ttl',
                '17 3 * * *',  -- 03:17 UTC daily
                $sql$
                    DELETE FROM govt_collection_runs
                    WHERE started_at < NOW() - INTERVAL '90 days';
                $sql$
            )
        $cron$;
    ELSE
        RAISE NOTICE
          'pg_cron not installed — falling back to '
          'tasks.prune_govt_runs scheduled in Celery Beat.';
    END IF;
END
$$;
