-- Migration 109: allow 'fetching' as an intermediate status on pending_youtube_videos
--
-- The fetch_youtube_transcripts Celery task claims one row at a time using
-- FOR UPDATE SKIP LOCKED, then commits (releasing the row lock) before making
-- the network call to the relay. Without an intermediate status the row would
-- be re-visible as 'pending' between the claim commit and the update to
-- 'transcribed'/'failed', causing concurrent tasks to double-fetch the same
-- video. 'fetching' closes that window.
--
-- If the worker crashes mid-fetch, the 'fetching' row would be stranded. A
-- recovery pass (run manually or added to a future task) can reset them:
--   UPDATE pending_youtube_videos
--     SET status = 'pending'
--   WHERE status = 'fetching'
--     AND updated_at < NOW() - INTERVAL '30 minutes';

ALTER TABLE pending_youtube_videos
    DROP CONSTRAINT IF EXISTS pending_youtube_videos_status_check;

ALTER TABLE pending_youtube_videos
    ADD CONSTRAINT pending_youtube_videos_status_check
        CHECK (status IN (
            'pending',
            'fetching',
            'transcribed',
            'extracted',
            'no_transcript',
            'failed'
        ));
