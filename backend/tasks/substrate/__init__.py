"""
Sprint-0 substrate extraction.

Single-pass enrichment over the full article corpus. Per article:

  1. Re-fetch the HTML via trafilatura (with retries + UA spoof for tough sites).
  2. Parse the HTML for STRUCTURAL data (no LLM):
       - outbound links + anchor text + domain
       - inline images + captions + alt text
       - embedded videos (YouTube / Vimeo / native <video>)
       - embedded tweets (blockquote.twitter-tweet)
       - canonical URL
       - language tag (<html lang>)
       - hero image (og:image preferred, twitter:image fallback)
       - article body via trafilatura
       - word count + reading minutes + body quality
  3. Run a single GROQ call over title + body for SEMANTIC data:
       - article_type classifier
       - up to 5 locations with country / region / city
       - up to 6 events with date + actors + type
  4. Persist to articles + article_links + article_media + article_locations
     + article_events.

Idempotent on `articles.substrate_processed_at` — re-running picks up
where the previous run left off.

Replaces ad-hoc per-feature extraction passes; ALL sprint 1+ features
read from the data this pass produces.
"""
