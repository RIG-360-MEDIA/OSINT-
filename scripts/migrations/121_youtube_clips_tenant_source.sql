-- 121: allow tenant-tagged TV ingestion in youtube_clips_v2.transcript_source.
-- Karnataka TV is ingested via Scout keyword-search + free-transcript providers
-- (box-native, no relay) and tagged transcript_source='ka_scout' so per-org
-- candidate selection keeps tenants' TV separate. Additive only — existing
-- 'auto_captions'/'manual_captions' rows and the Telangana pipeline are unaffected.
-- Idempotent.
ALTER TABLE youtube_clips_v2 DROP CONSTRAINT IF EXISTS youtube_clips_v2_transcript_source_check;
ALTER TABLE youtube_clips_v2 ADD CONSTRAINT youtube_clips_v2_transcript_source_check
  CHECK (transcript_source = ANY (ARRAY['manual_captions', 'auto_captions', 'ka_scout']));
