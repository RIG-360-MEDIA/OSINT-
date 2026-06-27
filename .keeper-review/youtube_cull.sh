#!/bin/sh
# RIG: bound the pending YouTube fetch queue. Discovery (~2400/day) far exceeds the
# single-residential-IP fetch ceiling (~480/day), so the queue grows unboundedly.
# Combined with newest-first fetch ordering, this skips pending videos older than 1 day
# so the relay always works the freshest ~20/hr and the stale tail doesn't pile up.
# Runs hourly via /etc/cron.d/rig-youtube-cull.
docker exec rig-postgres psql -U rig -d rig -c "UPDATE pending_youtube_videos SET status='skipped', updated_at=now() WHERE status='pending' AND discovered_at < now() - interval '1 day'"
