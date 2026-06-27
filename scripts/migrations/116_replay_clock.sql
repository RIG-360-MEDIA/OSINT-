-- 116_replay_clock.sql
--
-- analytics.now_sim_date() returns COALESCE(sim_now, NOW())::DATE from
-- analytics.replay_clock WHERE id = 1 — a "simulated today" used by the
-- entities / emerging / horizon endpoints to gate their time windows.
--
-- The function shipped but its backing table was never created, so every call
-- raised: relation "analytics.replay_clock" does not exist — 500-ing
-- /api/brief/entities, /api/brief/emerging and /api/brief/horizon.
--
-- Create the table with sim_now = NULL so now_sim_date() falls back to real
-- NOW() (live production time). To freeze the desk to a replay date later,
-- UPDATE analytics.replay_clock SET sim_now = '<ts>' WHERE id = 1.
CREATE TABLE IF NOT EXISTS analytics.replay_clock (
    id      INTEGER PRIMARY KEY,
    sim_now TIMESTAMPTZ
);

INSERT INTO analytics.replay_clock (id, sim_now)
VALUES (1, NULL)
ON CONFLICT (id) DO NOTHING;

GRANT SELECT ON analytics.replay_clock TO analytics_user;
