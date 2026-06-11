#!/bin/bash
# Apply migration 074 in deadlock-safe batches using pure psql loop.
# Runs inside rig-postgres container.
set -e

PSQL="psql -U rig -d rig -tAc"

echo "=== Setup function + trigger + backup ==="

$PSQL "CREATE TABLE IF NOT EXISTS article_locations_scope_backup_20260528 AS
       SELECT id, location_scope FROM article_locations WHERE 1=0;"

$PSQL "INSERT INTO article_locations_scope_backup_20260528 (id, location_scope)
       SELECT l.id, l.location_scope FROM article_locations l
        LEFT JOIN article_locations_scope_backup_20260528 b ON b.id = l.id
        WHERE b.id IS NULL;"

$PSQL "CREATE OR REPLACE FUNCTION compute_location_scope(
         p_location_text text, p_country text, p_region text, p_city text
       ) RETURNS text AS \$f\$
       DECLARE v_norm text;
       BEGIN
         v_norm := LOWER(TRIM(COALESCE(p_location_text, '')));
         IF v_norm IN (
           'africa','asia','europe','north america','south america',
           'oceania','antarctica','eurasia','middle east'
         ) THEN RETURN 'continent'; END IF;
         IF p_city    IS NOT NULL AND TRIM(p_city)    != '' THEN RETURN 'city';    END IF;
         IF p_region  IS NOT NULL AND TRIM(p_region)  != '' THEN RETURN 'state';   END IF;
         IF p_country IS NOT NULL AND TRIM(p_country) != '' THEN RETURN 'country'; END IF;
         RETURN 'unknown';
       END;
       \$f\$ LANGUAGE plpgsql IMMUTABLE;"

$PSQL "CREATE OR REPLACE FUNCTION trg_set_location_scope() RETURNS trigger AS \$f\$
       BEGIN
         NEW.location_scope := compute_location_scope(
           NEW.location_text, NEW.country, NEW.region, NEW.city
         );
         RETURN NEW;
       END;
       \$f\$ LANGUAGE plpgsql;"

$PSQL "DROP TRIGGER IF EXISTS trg_article_locations_scope ON article_locations;"
$PSQL "CREATE TRIGGER trg_article_locations_scope
         BEFORE INSERT OR UPDATE OF location_text, country, region, city
         ON article_locations
         FOR EACH ROW EXECUTE FUNCTION trg_set_location_scope();"

echo "  done"
echo ""
echo "=== Pre-state ==="
psql -U rig -d rig -c "SELECT location_scope, COUNT(*) FROM article_locations GROUP BY 1 ORDER BY 2 DESC LIMIT 8;"

echo ""
echo "=== Batched backfill ==="
TOTAL=$($PSQL "SELECT COUNT(*) FROM article_locations;")
BATCH=5000
BATCH_NUM=0
START_TS=$(date +%s)

while true; do
  $PSQL "WITH batch AS (
           SELECT id FROM article_locations
            WHERE location_scope IS DISTINCT FROM compute_location_scope(location_text, country, region, city)
            LIMIT $BATCH FOR UPDATE SKIP LOCKED
         )
         UPDATE article_locations l
            SET location_scope = compute_location_scope(l.location_text, l.country, l.region, l.city)
           FROM batch
          WHERE l.id = batch.id;" > /dev/null

  REMAINING=$($PSQL "SELECT COUNT(*) FROM article_locations
                     WHERE location_scope IS DISTINCT FROM compute_location_scope(location_text, country, region, city);")
  BATCH_NUM=$((BATCH_NUM + 1))
  UPDATED=$((TOTAL - REMAINING))
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TS))
  RATE=$((UPDATED / (ELAPSED + 1)))
  echo "  batch $BATCH_NUM | updated=$UPDATED/$TOTAL | remaining=$REMAINING | ${RATE} rows/s"

  if [ "$REMAINING" = "0" ]; then break; fi
  if [ "$BATCH_NUM" -gt 200 ]; then echo "WARN: batch ceiling"; break; fi
  sleep 0.1
done

echo ""
echo "=== Post-state ==="
psql -U rig -d rig -c "SELECT location_scope, COUNT(*) FROM article_locations GROUP BY 1 ORDER BY 2 DESC;"

echo ""
echo "=== Sample 12 random rows ==="
psql -U rig -d rig -c "SELECT location_text, city, region, country, location_scope
                         FROM article_locations ORDER BY random() LIMIT 12;"
