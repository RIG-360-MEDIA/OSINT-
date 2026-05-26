-- Sprint 0.6 — auto-bucket Telangana + Andhra Pradesh entities for
-- the Telangana government user (db4b9207). Idempotent via ON CONFLICT.

DO $seed$
DECLARE
  uid uuid := 'db4b9207-51aa-4d39-a7bf-e6fab34c3465';
  v_allies      int;
  v_opponents   int;
  v_neutrals    int;
  v_watched     int;
BEGIN
  -- 1. Allies: TG/AP Congress + AIMIM persons
  INSERT INTO user_watched_entities (user_id, entity_id, bucket, weight, source)
  SELECT uid, e.id, 'ally', 8, 'auto_party'
  FROM entity_dictionary e
  WHERE e.entity_type = 'person'
    AND LOWER(e.state) IN ('telangana', 'andhra pradesh')
    AND (LOWER(e.party) LIKE '%indian national congress%'
         OR LOWER(e.party) = 'inc'
         OR LOWER(e.party) = 'aimim'
         OR LOWER(e.party) LIKE '%majlis-e-ittehadul muslimeen%')
  ON CONFLICT (user_id, entity_id) DO NOTHING;
  GET DIAGNOSTICS v_allies = ROW_COUNT;

  -- 2. Opponents: Telangana BRS + BJP + TRS persons
  INSERT INTO user_watched_entities (user_id, entity_id, bucket, weight, source)
  SELECT uid, e.id, 'opponent', 8, 'auto_party'
  FROM entity_dictionary e
  WHERE e.entity_type = 'person'
    AND LOWER(e.state) = 'telangana'
    AND (LOWER(e.party) LIKE '%bharat rashtra samithi%'
         OR LOWER(e.party) = 'brs'
         OR LOWER(e.party) LIKE '%bharatiya janata party%'
         OR LOWER(e.party) = 'bjp'
         OR LOWER(e.party) LIKE '%telangana rashtra samithi%'
         OR LOWER(e.party) = 'trs')
  ON CONFLICT (user_id, entity_id) DO NOTHING;
  GET DIAGNOSTICS v_opponents = ROW_COUNT;

  -- 3. Neutrals: remaining TG + AP persons (untagged or other parties)
  INSERT INTO user_watched_entities (user_id, entity_id, bucket, weight, source)
  SELECT uid, e.id, 'neutral', 5, 'auto_party'
  FROM entity_dictionary e
  WHERE e.entity_type = 'person'
    AND LOWER(e.state) IN ('telangana', 'andhra pradesh')
    AND e.id NOT IN (
      SELECT entity_id FROM user_watched_entities WHERE user_id = uid
    )
  ON CONFLICT (user_id, entity_id) DO NOTHING;
  GET DIAGNOSTICS v_neutrals = ROW_COUNT;

  -- 4. Watched: TG/AP locations + constituencies + organizations
  INSERT INTO user_watched_entities (user_id, entity_id, bucket, weight, source)
  SELECT uid, e.id, 'watched', 5, 'auto_geo'
  FROM entity_dictionary e
  WHERE e.entity_type IN ('location', 'constituency', 'organization', 'org', 'organisation')
    AND LOWER(e.state) IN ('telangana', 'andhra pradesh')
  ON CONFLICT (user_id, entity_id) DO NOTHING;
  GET DIAGNOSTICS v_watched = ROW_COUNT;

  RAISE NOTICE 'allies=%  opponents=%  neutrals=%  watched=%',
               v_allies, v_opponents, v_neutrals, v_watched;
END $seed$;
