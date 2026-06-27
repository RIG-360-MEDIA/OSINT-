#!/usr/bin/env bash
# Durable guard: recover substrate rows orphaned in 'processing' by a hard-killed
# worker (container recreate / SIGKILL mid-batch). Without this, each restart
# leaks its in-flight batch and the claimable pool decays to zero -> summary
# coverage craters (the 2026-06-26 9.4k-row wedge: drain logged "processing 200"
# but processed=0 because the claim query only takes substrate_status NULL/'pending'
# while the count query counts everything unprocessed).
#
# Safe by construction:
#   - collected_at age gate (> 20 min) protects live in-flight rows, which are
#     always the NEWEST-collected (drain claims ORDER BY collected_at DESC).
#   - FOR UPDATE SKIP LOCKED avoids deadlock with workers finishing a row
#     (process_one's terminal UPDATE) and never waits on a held row.
#
# Deployed on Hetzner via /etc/cron.d/rig-substrate-orphan-reset (every 10 min).
N=$(docker exec rig-postgres psql -U rig -d rig -At -c "
  WITH r AS (
    UPDATE articles SET substrate_status='pending'
     WHERE id IN (
       SELECT id FROM articles
        WHERE substrate_status='processing'
          AND substrate_processed_at IS NULL
          AND collected_at < now() - interval '20 min'
        ORDER BY id
        FOR UPDATE SKIP LOCKED
     )
    RETURNING 1)
  SELECT count(*) FROM r;")
echo "$(date -u +%FT%TZ) reset_orphans=${N}"
