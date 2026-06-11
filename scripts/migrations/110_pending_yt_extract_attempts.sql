-- Migration 110: extraction retry counter on pending_youtube_videos
--
-- Before this, run_extraction_batch marked a video 'extracted' UNCONDITIONALLY
-- — even when every Groq chunk call failed (429 / JSON parse). The video was
-- then invisible to the beat (which only picks 'transcribed'), so a transient
-- rate-limit permanently stranded it with zero clips. 385 videos were lost this
-- way on 2026-06-10.
--
-- The fix leaves a video 'transcribed' when extraction wholly failed (no chunk
-- succeeded) so the beat retries it. extract_attempts bounds that retry loop:
-- after EXTRACT_MAX_ATTEMPTS wholly-failed passes the row goes to 'failed'.

ALTER TABLE pending_youtube_videos
    ADD COLUMN IF NOT EXISTS extract_attempts INTEGER NOT NULL DEFAULT 0;
