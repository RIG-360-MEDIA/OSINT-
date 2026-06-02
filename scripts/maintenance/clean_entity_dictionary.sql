-- One-time entity_dictionary cleanup — 2026-06-02
-- Removes garbage canonical entries: sports tournaments + election-seat STATS + bio
-- fragments mis-typed as 'person' (e.g. "1st ODI, India tour of England", "Opposition
-- NDA Seats: 24", "Defected from BJP to TMC; Died on 23 February 2026"). Their short /
-- place-name aliases (England, India, Trophy, NDA) were the cross-entity pollution source
-- that surfaced junk as top-prominence entities.
--
-- Backup taken first: entity_dictionary_bak_20260602 (full table, recoverable).
-- Pairs with the nlp_entities word-boundary + surface-form prominence fix (same day).
-- Applied live on 2026-06-02; recorded here for reproducibility. 99 rows removed
-- (17,165 -> 17,066). Bumping entity_dict_meta.version makes the live workers hot-reload
-- the cleaned dictionary within ~5 min (check_and_reload_if_stale).

BEGIN;

DELETE FROM entity_dictionary
WHERE canonical_name ~ ';'
   OR (entity_type = 'person' AND canonical_name ~* '(world cup|champions trophy|\yodi\y|\yt20i?\y|\ytest\y|tour of| vs |trophy|premier league|\yipl\y)')
   OR canonical_name ~* '\y(defected|resigned|sworn in|re-?elected|seats)\y';

UPDATE entity_dict_meta
   SET version = version + 1,
       entry_count = (SELECT count(*) FROM entity_dictionary)
 WHERE id = 1;

COMMIT;
