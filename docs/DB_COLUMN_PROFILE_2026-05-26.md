# RIG-Surveillance Per-Column Quality Profile (fast pass)

Generated: 2026-05-26T21:46:30.769367+00:00


## `article_links` — 4,774,569 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 4774569 |
| `article_id` | uuid | 0.0% | 93260 |
| `outbound_url` | text | 0.0% | 350588 |
| `outbound_url_normalized` | text | 0.0% | 170290 |
| `outbound_domain` | text | 0.0% | 8463 |
| `anchor_text` | text | 0.0% | 146987 |
| `link_type` | text | 0.0% | 2 |
| `position` | smallint | 0.0% | 120 |
| `created_at` | timestamp with time zone | 0.0% | 93258 |

## `article_media` — 1,396,074 rows · 12 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 1396074 |
| `article_id` | uuid | 0.0% | 94487 |
| `media_type` | text | 0.0% | 3 |
| `url` | text | 0.0% | 187169 |
| `external_id` | text | 99.7% | 2636 |
| `caption` | text | 99.9% | 313 |
| `alt_text` | text | 33.3% | 99232 |
| `width` | smallint | 58.3% | 1587 |
| `height` | smallint | 59.0% | 1700 |
| `position` | smallint | 0.0% | 65 |
| `is_hero` | boolean | 0.0% | 2 |
| `created_at` | timestamp with time zone | 0.0% | 94485 |

## `article_claims` — 306,278 rows · 11 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 306278 |
| `article_id` | uuid | 0.0% | 85891 |
| `claim_text` | text | 0.0% | 301209 |
| `subject_entity_id` | uuid | 86.0% | 4534 |
| `subject_text` | text | 0.0% | 35248 |
| `predicate` | text | 93.5% | 11021 |
| `object_text` | text | 93.7% | 18574 |
| `confidence` | real | 0.0% | 3 |
| `embedding` | USER-DEFINED | 1.4% | n/a |
| `extracted_at` | timestamp with time zone | 0.0% | 85895 |
| `extracted_by_model` | text | 0.0% | 1 |

## `article_locations` — 251,167 rows · 13 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 251167 |
| `article_id` | uuid | 0.0% | 85515 |
| `location_text` | text | 0.0% | 38856 |
| `country` | text | 8.8% | 276 |
| `region` | text | 67.3% | 2534 |
| `city` | text | 56.3% | 11181 |
| `lat` | numeric | 80.3% | 62 |
| `lng` | numeric | 80.3% | 63 |
| `confidence` | numeric | 0.0% | 1 |
| `mention_count` | smallint | 0.0% | 1 |
| `is_primary` | boolean | 0.0% | 2 |
| `created_at` | timestamp with time zone | 0.0% | 85514 |
| `location_scope` | text | 0.0% | 6 |

## `article_numbers` — 240,114 rows · 7 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 240114 |
| `article_id` | uuid | 0.0% | 68925 |
| `value` | text | 0.0% | 49543 |
| `unit` | text | 10.1% | 10303 |
| `context` | text | 0.0% | 197072 |
| `position` | smallint | 0.0% | 5 |
| `created_at` | timestamp with time zone | 0.0% | 68924 |

## `article_events` — 200,582 rows · 12 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 200582 |
| `article_id` | uuid | 0.0% | 82510 |
| `event_date` | date | 41.8% | 3796 |
| `event_description` | text | 0.0% | 183612 |
| `event_type` | text | 0.0% | 581 |
| `actors` | ARRAY | 0.0% | n/a |
| `confidence` | numeric | 0.0% | 1 |
| `position` | smallint | 0.0% | 6 |
| `created_at` | timestamp with time zone | 0.0% | 82509 |
| `is_future` | boolean | 0.0% | 2 |
| `event_cluster_id` | uuid | 99.8% | 358 |
| `effective_event_date` | date | 58.8% | 2203 |

## `article_stances` — 204,207 rows · 7 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 204207 |
| `article_id` | uuid | 0.0% | 76773 |
| `actor` | text | 0.0% | 76170 |
| `stance` | text | 0.0% | 42 |
| `intensity` | numeric | 0.0% | 13 |
| `actor_entity_id` | uuid | 50.2% | 5446 |
| `created_at` | timestamp with time zone | 0.0% | 76772 |

## `article_quotes` — 124,823 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 124823 |
| `article_id` | uuid | 0.0% | 57190 |
| `speaker_name` | text | 0.0% | 44460 |
| `speaker_entity_id` | uuid | 56.3% | 4432 |
| `quote_text` | text | 0.0% | 118663 |
| `char_offset_start` | integer | 25.7% | 2442 |
| `char_offset_end` | integer | 25.7% | 2488 |
| `is_direct` | boolean | 0.0% | 2 |
| `extracted_at` | timestamp with time zone | 0.0% | 57190 |
| `extracted_by_model` | text | 0.0% | 1 |
| `quote_text_en` | text | 97.5% | 3144 |
| `speaker_name_en` | text | 97.5% | 1579 |
| `translated_at` | timestamp with time zone | 97.5% | 3153 |
| `context` | text | 1.8% | 89636 |

## `articles` — 113,690 rows · 47 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 113690 |
| `source_id` | uuid | 0.0% | 333 |
| `url` | text | 0.0% | 113690 |
| `url_hash` | text | 0.0% | 113690 |
| `title` | text | 0.0% | 109617 |
| `lead_text_original` | text | 2.1% | 87643 |
| `lead_text_translated` | text | 1.9% | 98628 |
| `full_text_scraped` | text | 0.5% | 101866 |
| `language_detected` | character varying | 3.0% | 34 |
| `published_at` | timestamp with time zone | 1.9% | 96031 |
| `collected_at` | timestamp with time zone | 0.0% | 112985 |
| `nlp_processed` | boolean | 0.0% | 2 |
| `is_duplicate` | boolean | 0.0% | 2 |
| `duplicate_of` | uuid | 68.0% | 18087 |
| `content_type` | text | 0.0% | 1 |
| `source_tier` | integer | 0.8% | 3 |
| `thumbnail_url` | text | 9.8% | 88528 |
| `topic_category` | text | 1.5% | 15 |
| `geo_primary` | text | 24.3% | 10454 |
| `entities_extracted` | jsonb | 0.0% | n/a |
| `labse_embedding` | USER-DEFINED | 1.9% | n/a |
| `thread_id` | uuid | 4.3% | 7024 |
| `nlp_confidence` | text | 0.0% | 3 |
| `updated_at` | timestamp with time zone | 0.0% | 112985 |
| `claims_extracted` | boolean | 0.0% | 2 |
| `quotes_extracted` | boolean | 0.0% | 2 |
| `narrative_frame` | text | 100.0% | 0 |
| `fts` | tsvector | 0.0% | n/a |
| `body_quality` | text | 0.0% | 4 |
| `word_count` | integer | 15.8% | 3034 |
| `reading_minutes` | smallint | 15.8% | 72 |
| `article_type` | text | 15.6% | 13 |
| `canonical_url` | text | 76.3% | 23818 |
| `language_iso` | text | 16.1% | 13 |
| `substrate_processed_at` | timestamp with time zone | 0.0% | 113674 |
| `substrate_status` | text | 0.0% | 4 |
| `summary_preview` | text | 23.0% | 85986 |
| `summary_snippet` | text | 23.0% | 87277 |
| `summary_executive` | text | 23.0% | 87489 |
| `primary_subject` | text | 23.0% | 86600 |
| `register_style` | text | 23.2% | 20 |
| `register_emotion` | text | 23.2% | 53 |
| `register_is_breaking` | boolean | 0.0% | 2 |
| `full_text_translated` | text | 85.3% | 16761 |
| `extraction_version` | smallint | 0.0% | 3 |
| `byline` | text | 60.4% | 5584 |
| `author_name` | text | 99.9% | 1 |

## `user_article_relevance` — 110,097 rows · 11 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 110097 |
| `user_id` | uuid | 0.0% | 1 |
| `article_id` | uuid | 0.0% | 110097 |
| `score_stage1` | double precision | 0.0% | 1041 |
| `score_final` | double precision | 0.0% | 337 |
| `relevance_tier` | integer | 0.0% | 4 |
| `relevance_explanation` | text | 87.1% | 8982 |
| `sentiment_for_user` | text | 87.1% | 3 |
| `geo_multiplier_applied` | double precision | 0.0% | 3 |
| `matched_entity_names` | ARRAY | 0.0% | n/a |
| `scored_at` | timestamp with time zone | 0.0% | 8174 |

## `cm_stance_scores` — 106,911 rows · 10 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 106911 |
| `source_kind` | text | 0.0% | 2 |
| `source_id` | uuid | 0.0% | 106911 |
| `state` | text | 95.3% | 2 |
| `stance` | text | 0.0% | 5 |
| `party` | text | 100.0% | 0 |
| `party_kind` | text | 0.0% | 1 |
| `confidence` | real | 0.0% | 13 |
| `model` | text | 0.0% | 3 |
| `scored_at` | timestamp with time zone | 0.0% | 2885 |

## `article_districts` — 28,037 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `article_id` | uuid | 0.0% | 17262 |
| `district_id` | text | 0.0% | 59 |
| `mention_count` | integer | 0.0% | 30 |
| `confidence` | real | 0.0% | 19 |
| `is_primary` | boolean | 0.0% | 2 |
| `inserted_at` | timestamp with time zone | 0.0% | 15145 |

## `entity_dictionary` — 15,755 rows · 8 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 15755 |
| `canonical_name` | text | 0.0% | 15755 |
| `entity_type` | text | 0.0% | 7 |
| `aliases` | ARRAY | 0.0% | n/a |
| `state` | text | 44.0% | 147 |
| `party` | text | 79.5% | 433 |
| `metadata` | jsonb | 0.0% | n/a |
| `created_at` | timestamp with time zone | 0.0% | 285 |

## `cm_lead_headlines` — 13,835 rows · 11 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 13835 |
| `state_code` | text | 0.0% | 1 |
| `rank` | integer | 0.0% | 5 |
| `eyebrow` | text | 0.0% | 2414 |
| `headline` | text | 0.0% | 7386 |
| `cite_ids` | ARRAY | 0.0% | n/a |
| `generated_at` | timestamp with time zone | 0.0% | 2768 |
| `model` | text | 0.0% | 2 |
| `validated` | boolean | 0.0% | 1 |
| `rejected` | boolean | 0.0% | 1 |
| `rejection_reason` | text | 100.0% | 0 |

## `youtube_clips` — 12,764 rows · 21 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 12764 |
| `video_id` | text | 0.0% | 9678 |
| `video_title` | text | 0.0% | 9352 |
| `channel_id` | text | 0.0% | 65 |
| `channel_name` | text | 0.0% | 58 |
| `video_published_at` | timestamp with time zone | 6.0% | 8899 |
| `video_url` | text | 0.0% | 9678 |
| `clip_start_seconds` | integer | 0.0% | 222 |
| `clip_end_seconds` | integer | 0.0% | 231 |
| `embed_url` | text | 0.0% | 10058 |
| `transcript_segment` | text | 0.0% | 8009 |
| `transcript_language` | text | 0.0% | 5 |
| `transcript_translated` | text | 0.0% | 11617 |
| `matched_entity` | text | 0.0% | 65 |
| `matched_entity_type` | text | 100.0% | 0 |
| `labse_embedding` | USER-DEFINED | 4.1% | n/a |
| `relevance_score` | double precision | 0.0% | 2 |
| `collected_at` | timestamp with time zone | 0.0% | 3440 |
| `processed` | boolean | 0.0% | 1 |
| `transcript_source` | text | 0.0% | 3 |
| `confidence` | numeric | 0.0% | 7 |

## `story_threads` — 7,409 rows · 15 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 7409 |
| `title` | text | 0.0% | 7399 |
| `primary_entities` | ARRAY | 0.0% | n/a |
| `article_count` | integer | 0.0% | 227 |
| `source_count` | integer | 0.0% | 3 |
| `momentum` | text | 0.0% | 3 |
| `centroid_embedding` | USER-DEFINED | 0.0% | n/a |
| `first_seen_at` | timestamp with time zone | 0.0% | 1619 |
| `last_updated_at` | timestamp with time zone | 0.0% | 1389 |
| `is_active` | boolean | 0.0% | 2 |
| `seed_article_id` | uuid | 94.2% | 430 |
| `seed_embedding` | USER-DEFINED | 94.2% | n/a |
| `confidence_score` | real | 94.2% | 8 |
| `cluster_version` | smallint | 0.0% | 2 |
| `last_evaluated_at` | timestamp with time zone | 94.2% | 430 |

## `entity_mention_daily` — 7,325 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 7325 |
| `entity_text` | text | 0.0% | 6205 |
| `date` | date | 0.0% | 5 |
| `n_claims` | integer | 0.0% | 17 |
| `n_quotes` | integer | 0.0% | 19 |
| `n_stances` | integer | 0.0% | 21 |
| `n_sources` | integer | 0.0% | 16 |
| `n_mentions_total` | integer | 0.0% | 32 |
| `computed_at` | timestamp with time zone | 0.0% | 42 |

## `event_clusters` — 6,859 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 6859 |
| `canonical_description` | text | 0.0% | 6751 |
| `canonical_actors` | ARRAY | 0.0% | n/a |
| `canonical_event_type` | text | 0.0% | 133 |
| `canonical_date` | date | 0.0% | 1273 |
| `is_future` | boolean | 0.0% | 2 |
| `article_count` | integer | 0.0% | 16 |
| `source_count` | integer | 0.0% | 11 |
| `confidence_score` | real | 0.0% | 517 |
| `first_seen_at` | timestamp with time zone | 0.0% | 6859 |
| `last_updated_at` | timestamp with time zone | 0.0% | 6859 |
| `is_active` | boolean | 0.0% | 2 |
| `importance_score` | real | 2.1% | 3031 |
| `importance_updated_at` | timestamp with time zone | 2.1% | 1 |

## `social_posts` — 6,890 rows · 26 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 6890 |
| `platform` | text | 0.0% | 2 |
| `platform_post_id` | text | 0.0% | 6890 |
| `monitor_id` | uuid | 0.0% | 28 |
| `author_username` | text | 0.0% | 1594 |
| `author_display_name` | text | 100.0% | 0 |
| `author_follower_count` | integer | 100.0% | 0 |
| `post_text` | text | 0.0% | 6827 |
| `post_text_translated` | text | 43.3% | 3896 |
| `post_language` | text | 0.0% | 30 |
| `post_url` | text | 0.0% | 6890 |
| `upvotes` | integer | 0.0% | 193 |
| `downvotes` | integer | 0.0% | 1 |
| `comment_count` | integer | 0.0% | 71 |
| `share_count` | integer | 0.0% | 1 |
| `forward_count` | integer | 0.0% | 6 |
| `forwarded_from` | text | 0.0% | 1 |
| `has_document` | boolean | 0.0% | 2 |
| `document_url` | text | 95.5% | 310 |
| `sentiment_score` | double precision | 0.0% | 1111 |
| `matched_entities` | ARRAY | 0.0% | n/a |
| `topic_category` | text | 100.0% | 0 |
| `labse_embedding` | USER-DEFINED | 4.5% | n/a |
| `posted_at` | timestamp with time zone | 0.0% | 6829 |
| `collected_at` | timestamp with time zone | 0.0% | 562 |
| `relevance_score` | integer | 0.0% | 15 |

## `cm_issue_evidence` — 5,810 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `issue_id` | bigint | 0.0% | 296 |
| `source_kind` | text | 0.0% | 1 |
| `source_id` | uuid | 0.0% | 1560 |
| `side` | text | 100.0% | 0 |
| `weight` | real | 0.0% | 1 |
| `attached_at` | timestamp with time zone | 0.0% | 160 |

## `newspaper_clippings` — 5,170 rows · 24 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 5170 |
| `newspaper_id` | uuid | 0.0% | 37 |
| `newspaper_name` | text | 0.0% | 37 |
| `newspaper_language` | text | 0.0% | 9 |
| `edition_date` | date | 0.0% | 15 |
| `page_number` | integer | 0.0% | 25 |
| `headline` | text | 0.0% | 4712 |
| `headline_translated` | text | 60.2% | 1871 |
| `article_text` | text | 0.0% | 5110 |
| `article_text_translated` | text | 60.2% | 2039 |
| `bbox_left` | double precision | 0.0% | 636 |
| `bbox_bottom` | double precision | 0.0% | 1335 |
| `bbox_right` | double precision | 0.0% | 698 |
| `bbox_top` | double precision | 0.0% | 1380 |
| `clipping_image_b64` | text | 10.8% | 4404 |
| `topic_category` | text | 100.0% | 0 |
| `geo_primary` | text | 100.0% | 0 |
| `entities_extracted` | jsonb | 0.0% | n/a |
| `relevance_score` | double precision | 0.0% | 3 |
| `relevance_explanation` | text | 0.0% | 94 |
| `labse_embedding` | USER-DEFINED | 0.9% | n/a |
| `sentiment` | text | 15.0% | 3 |
| `narrative_angle` | text | 100.0% | 0 |
| `collected_at` | timestamp with time zone | 0.0% | 409 |

## `cm_spokesperson_quotes` — 4,993 rows · 16 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 4993 |
| `source_kind` | text | 0.0% | 1 |
| `source_id` | uuid | 0.0% | 2326 |
| `state` | text | 92.4% | 2 |
| `speaker` | text | 0.0% | 1971 |
| `speaker_canonical` | text | 76.9% | 248 |
| `party` | text | 43.0% | 143 |
| `role` | text | 9.4% | 654 |
| `quote` | text | 0.0% | 4879 |
| `quote_lang` | text | 100.0% | 0 |
| `stance` | text | 0.0% | 5 |
| `sentiment` | real | 100.0% | 0 |
| `issue_id` | bigint | 99.7% | 1 |
| `issue_hint` | text | 0.0% | 3637 |
| `source_url` | text | 0.0% | 2326 |
| `extracted_at` | timestamp with time zone | 0.0% | 1106 |

## `govt_collection_runs` — 2,076 rows · 13 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 2076 |
| `source_id` | uuid | 0.0% | 50 |
| `source_name` | text | 0.0% | 51 |
| `started_at` | timestamp with time zone | 0.0% | 1980 |
| `finished_at` | timestamp with time zone | 0.0% | 1980 |
| `status` | text | 0.0% | 1 |
| `urls_discovered` | integer | 0.0% | 34 |
| `urls_filtered_junk` | integer | 0.0% | 20 |
| `pdfs_downloaded` | integer | 0.0% | 30 |
| `pdfs_extracted` | integer | 0.0% | 1 |
| `docs_inserted` | integer | 0.0% | 18 |
| `docs_failed` | integer | 0.0% | 20 |
| `error_summary` | text | 100.0% | 0 |

## `social_entity_baselines` — 465 rows · 8 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | integer | 0.0% | 465 |
| `entity` | text | 0.0% | 465 |
| `posts_24h` | integer | 0.0% | 16 |
| `posts_7d_mean` | double precision | 0.0% | 16 |
| `sentiment_24h` | double precision | 0.0% | 95 |
| `sentiment_7d` | double precision | 0.0% | 95 |
| `sources_24h` | integer | 0.0% | 6 |
| `computed_at` | timestamp with time zone | 0.0% | 1 |

## `article_tweets` — 1,608 rows · 19 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 1608 |
| `article_id` | uuid | 0.0% | 1122 |
| `tweet_id` | text | 0.0% | 1421 |
| `tweet_url` | text | 0.0% | 1436 |
| `author_handle` | text | 3.1% | 833 |
| `author_name` | text | 3.1% | 833 |
| `author_profile_url` | text | 3.1% | 833 |
| `tweet_text` | text | 3.1% | 1380 |
| `tweet_html` | text | 3.1% | 1381 |
| `language` | text | 3.1% | 31 |
| `posted_at` | date | 3.1% | 65 |
| `has_image` | boolean | 0.0% | 2 |
| `image_urls` | ARRAY | 0.0% | n/a |
| `hashtags` | ARRAY | 0.0% | n/a |
| `mentions` | ARRAY | 0.0% | n/a |
| `links_in_tweet` | ARRAY | 0.0% | n/a |
| `fetched_at` | timestamp with time zone | 0.0% | 1169 |
| `fetch_status` | text | 0.0% | 3 |
| `fetch_error` | text | 96.9% | 16 |

## `govt_document_chunks` — 1,148 rows · 11 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 1148 |
| `document_id` | uuid | 0.0% | 392 |
| `chunk_index` | integer | 0.0% | 5 |
| `chunk_text` | text | 0.0% | 1115 |
| `chunk_translated` | text | 100.0% | 0 |
| `labse_embedding` | USER-DEFINED | 2.2% | n/a |
| `page_number` | integer | 100.0% | 0 |
| `created_at` | timestamp with time zone | 0.0% | 53 |
| `section_heading` | text | 73.3% | 44 |
| `start_char` | integer | 1.6% | 404 |
| `end_char` | integer | 1.6% | 501 |

## `impersonation_actions` — 978 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 978 |
| `session_id` | uuid | 0.0% | 22 |
| `method` | text | 0.0% | 3 |
| `path` | text | 0.0% | 119 |
| `status_code` | integer | 0.0% | 3 |
| `at` | timestamp with time zone | 0.0% | 978 |

## `social_events` — 160 rows · 10 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 160 |
| `event_type` | text | 0.0% | 4 |
| `subject` | text | 0.0% | 152 |
| `subject_kind` | text | 0.0% | 3 |
| `magnitude` | double precision | 0.0% | 16 |
| `confidence` | text | 0.0% | 3 |
| `sources` | ARRAY | 0.0% | n/a |
| `body` | text | 0.0% | 154 |
| `detected_at` | timestamp with time zone | 0.0% | 1 |
| `metadata` | jsonb | 0.0% | n/a |

## `articles_embed_backup_20260523` — 801 rows · 3 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 801 |
| `old_sig` | text | 0.0% | 6 |
| `old_embedding` | USER-DEFINED | 0.0% | n/a |

## `sources` — 793 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 793 |
| `name` | text | 0.0% | 792 |
| `domain` | text | 0.0% | 793 |
| `rss_url` | text | 27.6% | 548 |
| `source_type` | text | 0.0% | 3 |
| `source_tier` | integer | 0.0% | 3 |
| `language` | text | 0.0% | 12 |
| `geo_states` | ARRAY | 0.0% | n/a |
| `topics` | ARRAY | 0.0% | n/a |
| `health_score` | double precision | 0.0% | 6 |
| `consecutive_failures` | integer | 0.0% | 7 |
| `is_active` | boolean | 0.0% | 2 |
| `last_collected_at` | timestamp with time zone | 33.2% | 530 |
| `created_at` | timestamp with time zone | 0.0% | 3 |

## `cm_action_queue` — 765 rows · 12 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 765 |
| `state_code` | text | 0.0% | 1 |
| `priority` | text | 0.0% | 3 |
| `text` | text | 0.0% | 765 |
| `deadline` | text | 0.0% | 50 |
| `source_type` | text | 0.0% | 1 |
| `rule_name` | text | 100.0% | 0 |
| `cite_ids` | ARRAY | 0.0% | n/a |
| `generated_at` | timestamp with time zone | 0.0% | 400 |
| `expires_at` | timestamp with time zone | 0.0% | 765 |
| `status` | text | 0.0% | 2 |
| `completed_at` | timestamp with time zone | 100.0% | 0 |

## `user_watched_entities` — 571 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `user_id` | uuid | 0.0% | 1 |
| `entity_id` | uuid | 0.0% | 571 |
| `bucket` | text | 0.0% | 4 |
| `weight` | smallint | 0.0% | 2 |
| `source` | text | 0.0% | 2 |
| `added_at` | timestamp with time zone | 0.0% | 1 |

## `dossier_finding` — 421 rows · 8 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 421 |
| `dossier_id` | uuid | 0.0% | 8 |
| `source` | text | 0.0% | 6 |
| `field` | text | 0.0% | 25 |
| `value` | jsonb | 0.0% | n/a |
| `source_url` | text | 0.0% | 89 |
| `confidence` | real | 0.0% | 6 |
| `found_at` | timestamp with time zone | 0.0% | 8 |

## `social_sentiment_daily` — 253 rows · 10 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 253 |
| `monitor_id` | uuid | 0.0% | 25 |
| `date` | date | 0.0% | 33 |
| `platform` | text | 0.0% | 2 |
| `positive_count` | integer | 0.0% | 9 |
| `negative_count` | integer | 0.0% | 9 |
| `neutral_count` | integer | 0.0% | 22 |
| `avg_sentiment` | double precision | 0.0% | 142 |
| `post_count` | integer | 0.0% | 23 |
| `top_entities` | ARRAY | 0.0% | n/a |

## `newspaper_editions` — 448 rows · 4 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `newspaper_id` | uuid | 0.0% | 37 |
| `edition_date` | date | 0.0% | 14 |
| `pdf_url` | text | 0.0% | 367 |
| `fetched_at` | timestamp with time zone | 0.0% | 448 |

## `govt_documents` — 392 rows · 31 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 392 |
| `source_id` | uuid | 0.0% | 18 |
| `source_name` | text | 0.0% | 18 |
| `source_geography` | text | 0.0% | 3 |
| `document_type` | text | 0.0% | 18 |
| `title` | text | 0.0% | 347 |
| `document_number` | text | 100.0% | 0 |
| `document_url` | text | 0.0% | 392 |
| `published_at` | timestamp with time zone | 38.3% | 59 |
| `full_text` | text | 0.0% | 388 |
| `full_text_translated` | text | 0.0% | 388 |
| `language_detected` | text | 0.0% | 8 |
| `page_count` | integer | 100.0% | 0 |
| `summary` | text | 99.2% | 3 |
| `topic_category` | text | 0.0% | 12 |
| `geo_primary` | text | 0.0% | 9 |
| `entities_extracted` | jsonb | 0.0% | n/a |
| `labse_embedding` | USER-DEFINED | 0.0% | n/a |
| `nlp_processed` | boolean | 0.0% | 1 |
| `collected_at` | timestamp with time zone | 0.0% | 53 |
| `updated_at` | timestamp with time zone | 0.0% | 40 |
| `intel_json` | jsonb | 0.0% | n/a |
| `intrinsic_importance` | double precision | 0.0% | 47 |
| `document_nature` | text | 0.0% | 12 |
| `action_posture` | text | 0.0% | 8 |
| `geography_affected` | jsonb | 0.0% | n/a |
| `financial_magnitude_inr` | bigint | 92.6% | 29 |
| `effective_date` | date | 54.1% | 78 |
| `winners` | jsonb | 0.0% | n/a |
| `losers` | jsonb | 0.0% | n/a |
| `enforcement_strength` | text | 33.7% | 3 |

## `social_monitors` — 55 rows · 12 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 55 |
| `platform` | text | 0.0% | 2 |
| `monitor_type` | text | 0.0% | 2 |
| `identifier` | text | 0.0% | 55 |
| `display_name` | text | 0.0% | 55 |
| `description` | text | 78.2% | 12 |
| `is_active` | boolean | 0.0% | 1 |
| `last_collected_at` | timestamp with time zone | 0.0% | 5 |
| `follower_count` | integer | 100.0% | 0 |
| `created_at` | timestamp with time zone | 0.0% | 5 |
| `tier` | text | 0.0% | 3 |
| `is_official` | boolean | 0.0% | 2 |

## `cm_issues` — 296 rows · 15 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 296 |
| `label` | text | 0.0% | 296 |
| `slug` | text | 0.0% | 296 |
| `state` | text | 6.4% | 2 |
| `embedding` | USER-DEFINED | 0.0% | n/a |
| `first_seen` | timestamp with time zone | 0.0% | 129 |
| `last_seen` | timestamp with time zone | 0.0% | 130 |
| `ruling_stance_summary` | text | 100.0% | 0 |
| `opposition_stance_summary` | text | 100.0% | 0 |
| `neutral_summary` | text | 100.0% | 0 |
| `volume_24h` | integer | 0.0% | 92 |
| `volume_7d` | integer | 0.0% | 1 |
| `intensity` | real | 0.0% | 1 |
| `trajectory` | text | 0.0% | 1 |
| `updated_at` | timestamp with time zone | 0.0% | 130 |

## `user_govt_doc_relevance` — 262 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 262 |
| `user_id` | uuid | 0.0% | 1 |
| `doc_id` | uuid | 0.0% | 262 |
| `score_stage1` | double precision | 0.0% | 76 |
| `score_final` | double precision | 0.0% | 76 |
| `relevance_tier` | integer | 0.0% | 3 |
| `relevance_explanation` | text | 100.0% | 0 |
| `urgency` | text | 2.7% | 2 |
| `suggested_action` | text | 32.1% | 157 |
| `why_it_matters` | text | 32.1% | 178 |
| `sentiment_for_user` | text | 2.7% | 1 |
| `matched_entity_names` | ARRAY | 0.0% | n/a |
| `geo_match_strength` | double precision | 0.0% | 4 |
| `computed_at` | timestamp with time zone | 0.0% | 262 |

## `analyst_sessions` — 192 rows · 5 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 192 |
| `user_id` | uuid | 0.0% | 2 |
| `created_at` | timestamp with time zone | 0.0% | 192 |
| `updated_at` | timestamp with time zone | 0.0% | 192 |
| `room` | text | 0.0% | 2 |

## `analyst_turns` — 163 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 163 |
| `session_id` | uuid | 0.0% | 142 |
| `question` | text | 0.0% | 102 |
| `answer` | text | 0.0% | 162 |
| `evidence_count` | integer | 0.0% | 18 |
| `confidence` | text | 0.0% | 3 |
| `retrieval_ms` | integer | 0.0% | 158 |
| `created_at` | timestamp with time zone | 0.0% | 163 |
| `room` | text | 0.0% | 2 |

## `top_stories_daily` — 114 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 114 |
| `date` | date | 0.0% | 14 |
| `user_id` | uuid | 87.7% | 1 |
| `stories` | jsonb | 0.0% | n/a |
| `generated_at` | timestamp with time zone | 0.0% | 114 |
| `generated_by_model` | text | 0.0% | 2 |

## `newsroom_entity_mentions` — 90 rows · 7 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 90 |
| `segment_id` | uuid | 0.0% | 6 |
| `entity_id` | uuid | 0.0% | 76 |
| `span_start` | integer | 0.0% | 26 |
| `span_end` | integer | 0.0% | 26 |
| `was_phonetic` | boolean | 0.0% | 2 |
| `created_at` | timestamp with time zone | 0.0% | 2 |

## `youtube_channels` — 72 rows · 18 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 72 |
| `channel_id` | text | 0.0% | 72 |
| `channel_name` | text | 0.0% | 72 |
| `channel_url` | text | 0.0% | 72 |
| `description` | text | 100.0% | 0 |
| `subscriber_count` | integer | 100.0% | 0 |
| `is_active` | boolean | 0.0% | 2 |
| `last_checked_at` | timestamp with time zone | 0.0% | 72 |
| `created_at` | timestamp with time zone | 0.0% | 1 |
| `tier` | text | 0.0% | 3 |
| `poll_priority` | integer | 0.0% | 4 |
| `quality_score` | numeric | 0.0% | 1 |
| `language` | text | 0.0% | 1 |
| `category` | text | 84.7% | 3 |
| `last_yielded_at` | timestamp with time zone | 100.0% | 0 |
| `consecutive_dry_polls` | integer | 0.0% | 1 |
| `last_video_published_at` | timestamp with time zone | 100.0% | 0 |
| `deactivated_reason` | text | 98.6% | 1 |

## `social_cluster_posts` — 61 rows · 2 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `cluster_id` | uuid | 0.0% | 28 |
| `post_id` | uuid | 0.0% | 61 |

## `user_entities` — 64 rows · 8 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 64 |
| `user_id` | uuid | 0.0% | 1 |
| `canonical_name` | text | 0.0% | 64 |
| `entity_type` | text | 0.0% | 6 |
| `aliases` | ARRAY | 0.0% | n/a |
| `why_watching` | text | 0.0% | 19 |
| `priority` | integer | 0.0% | 10 |
| `created_at` | timestamp with time zone | 0.0% | 7 |

## `districts` — 59 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | text | 0.0% | 59 |
| `state_code` | text | 0.0% | 2 |
| `name` | text | 0.0% | 59 |
| `hq_city` | text | 0.0% | 59 |
| `centroid_lat` | double precision | 0.0% | 59 |
| `centroid_lon` | double precision | 0.0% | 59 |
| `bbox` | jsonb | 100.0% | n/a |
| `aliases` | ARRAY | 0.0% | n/a |
| `inserted_at` | timestamp with time zone | 0.0% | 2 |

## `social_summaries` — 96 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 96 |
| `edition` | integer | 0.0% | 96 |
| `classification` | text | 0.0% | 1 |
| `generated_at` | timestamp with time zone | 0.0% | 96 |
| `window_hours` | integer | 0.0% | 1 |
| `body` | text | 0.0% | 96 |
| `event_ids` | ARRAY | 0.0% | n/a |
| `sources_used` | ARRAY | 0.0% | n/a |
| `metadata` | jsonb | 0.0% | n/a |

## `newspaper_sources` — 50 rows · 8 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 50 |
| `name` | text | 0.0% | 50 |
| `language` | text | 0.0% | 10 |
| `careerswave_url` | text | 0.0% | 50 |
| `direct_pdf_url` | text | 100.0% | 0 |
| `is_active` | boolean | 0.0% | 1 |
| `last_scraped_at` | timestamp with time zone | 26.0% | 37 |
| `created_at` | timestamp with time zone | 0.0% | 5 |

## `govt_document_sources` — 50 rows · 12 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 50 |
| `name` | text | 0.0% | 50 |
| `portal_url` | text | 0.0% | 50 |
| `source_geography` | text | 0.0% | 3 |
| `document_type` | text | 0.0% | 44 |
| `scrape_pattern` | text | 100.0% | 0 |
| `is_active` | boolean | 0.0% | 1 |
| `last_scraped_at` | timestamp with time zone | 0.0% | 50 |
| `created_at` | timestamp with time zone | 0.0% | 8 |
| `health_score` | double precision | 0.0% | 1 |
| `consecutive_failures` | integer | 0.0% | 1 |
| `since_days_override` | integer | 84.0% | 1 |

## `social_topic_seeds` — 41 rows · 4 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | integer | 0.0% | 41 |
| `term` | text | 0.0% | 41 |
| `weight` | integer | 0.0% | 1 |
| `note` | text | 0.0% | 12 |

## `newsroom_segments` — 37 rows · 18 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 37 |
| `broadcast_id` | uuid | 0.0% | 2 |
| `start_sec` | numeric | 0.0% | 36 |
| `end_sec` | numeric | 0.0% | 37 |
| `speaker_label` | text | 0.0% | 1 |
| `speaker_entity_id` | uuid | 86.5% | 5 |
| `text_native` | text | 0.0% | 37 |
| `text_en` | text | 0.0% | 33 |
| `confidence` | numeric | 0.0% | 8 |
| `l1_text` | text | 100.0% | 0 |
| `l2_text` | text | 0.0% | 37 |
| `l3_text` | text | 94.6% | 2 |
| `is_quote` | boolean | 0.0% | 2 |
| `is_editorial` | boolean | 0.0% | 2 |
| `sentiment` | numeric | 0.0% | 4 |
| `framing` | text | 0.0% | 3 |
| `is_live` | boolean | 0.0% | 1 |
| `created_at` | timestamp with time zone | 0.0% | 2 |

## `social_geo_seeds` — 30 rows · 4 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | integer | 0.0% | 30 |
| `term` | text | 0.0% | 30 |
| `kind` | text | 0.0% | 4 |
| `weight` | integer | 0.0% | 1 |

## `assembly_constituencies` — 29 rows · 13 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `code` | text | 0.0% | 29 |
| `state` | text | 0.0% | 1 |
| `number` | integer | 0.0% | 29 |
| `name` | text | 0.0% | 29 |
| `name_te` | text | 100.0% | 0 |
| `district` | text | 0.0% | 4 |
| `parliamentary` | text | 100.0% | 0 |
| `reservation` | text | 0.0% | 2 |
| `centroid_lat` | double precision | 100.0% | 0 |
| `centroid_lon` | double precision | 100.0% | 0 |
| `source_url` | text | 0.0% | 1 |
| `inserted_at` | timestamp with time zone | 0.0% | 1 |
| `state_code` | text | 0.0% | 1 |

## `social_clusters` — 28 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 28 |
| `window_start` | timestamp with time zone | 0.0% | 1 |
| `window_end` | timestamp with time zone | 0.0% | 1 |
| `headline` | text | 0.0% | 19 |
| `summary` | text | 0.0% | 27 |
| `post_count` | integer | 0.0% | 2 |
| `platforms` | ARRAY | 0.0% | n/a |
| `monitor_names` | ARRAY | 0.0% | n/a |
| `top_entities` | ARRAY | 0.0% | n/a |
| `avg_sentiment` | double precision | 0.0% | 11 |
| `sentiment_tone` | text | 0.0% | 3 |
| `representative_post_ids` | ARRAY | 0.0% | n/a |
| `sample_languages` | ARRAY | 0.0% | n/a |
| `created_at` | timestamp with time zone | 0.0% | 1 |

## `newsroom_channels` — 25 rows · 12 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 25 |
| `name` | text | 0.0% | 25 |
| `yt_handle` | text | 0.0% | 25 |
| `language` | text | 0.0% | 1 |
| `beat` | text | 0.0% | 1 |
| `is_live_24x7` | boolean | 0.0% | 2 |
| `active` | boolean | 0.0% | 2 |
| `created_at` | timestamp with time zone | 0.0% | 5 |
| `current_live_video_id` | text | 92.0% | 2 |
| `current_live_title` | text | 92.0% | 2 |
| `last_live_check_at` | timestamp with time zone | 16.0% | 21 |
| `last_live_at` | timestamp with time zone | 28.0% | 18 |

## `cm_risk_calendar` — 24 rows · 13 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 24 |
| `event_date` | date | 0.0% | 7 |
| `state` | text | 100.0% | 0 |
| `kind` | text | 0.0% | 1 |
| `title` | text | 0.0% | 24 |
| `description` | text | 0.0% | 2 |
| `source_id` | uuid | 0.0% | 24 |
| `source_kind` | text | 0.0% | 1 |
| `source_url` | text | 100.0% | 0 |
| `risk_summary` | text | 0.0% | 1 |
| `risk_level` | text | 0.0% | 2 |
| `inserted_at` | timestamp with time zone | 0.0% | 1 |
| `updated_at` | timestamp with time zone | 0.0% | 1 |

## `dossier_cache` — 22 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `cache_key` | text | 0.0% | 22 |
| `source` | text | 0.0% | 5 |
| `target_hash` | text | 0.0% | 18 |
| `payload` | jsonb | 0.0% | n/a |
| `fetched_at` | timestamp with time zone | 0.0% | 22 |
| `expires_at` | timestamp with time zone | 0.0% | 22 |

## `user_page_access` — 16 rows · 4 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `user_id` | uuid | 0.0% | 2 |
| `page_slug` | text | 0.0% | 9 |
| `granted_by` | uuid | 56.2% | 1 |
| `granted_at` | timestamp with time zone | 0.0% | 2 |

## `entity_aliases` — 14 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 14 |
| `canonical_name` | text | 0.0% | 6 |
| `alias` | text | 0.0% | 14 |
| `notes` | text | 0.0% | 10 |
| `region` | text | 0.0% | 1 |
| `created_at` | timestamp with time zone | 0.0% | 1 |

## `cm_promises` — 12 rows · 15 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 12 |
| `state` | text | 0.0% | 2 |
| `pledge_text` | text | 0.0% | 12 |
| `pledge_short` | text | 0.0% | 12 |
| `owner_party` | text | 0.0% | 2 |
| `source` | text | 0.0% | 2 |
| `source_url` | text | 0.0% | 2 |
| `pledged_at` | date | 0.0% | 2 |
| `deadline` | date | 100.0% | 0 |
| `status` | text | 0.0% | 4 |
| `status_confidence` | real | 0.0% | 5 |
| `last_status_change` | timestamp with time zone | 0.0% | 7 |
| `last_evidence_url` | text | 100.0% | 0 |
| `exploitation_index` | real | 0.0% | 5 |
| `last_scored_at` | timestamp with time zone | 0.0% | 1 |

## `cm_political_handles` — 9 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | bigint | 0.0% | 9 |
| `state` | text | 0.0% | 2 |
| `coalition` | text | 0.0% | 2 |
| `party` | text | 0.0% | 7 |
| `person_name` | text | 100.0% | 0 |
| `person_role` | text | 0.0% | 1 |
| `platform` | text | 0.0% | 1 |
| `handle` | text | 0.0% | 9 |
| `url` | text | 0.0% | 9 |
| `verified_url` | text | 100.0% | 0 |
| `active` | boolean | 0.0% | 1 |
| `cadence_minutes` | integer | 0.0% | 1 |
| `inserted_at` | timestamp with time zone | 0.0% | 1 |
| `state_code` | text | 22.2% | 2 |

## `cm_coalitions` — 9 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `state` | text | 0.0% | 2 |
| `party` | text | 0.0% | 7 |
| `coalition` | text | 0.0% | 2 |
| `since` | date | 0.0% | 2 |
| `source_url` | text | 0.0% | 1 |
| `inserted_at` | timestamp with time zone | 0.0% | 1 |

## `entity_dossier` — 9 rows · 12 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 9 |
| `user_id` | text | 0.0% | 2 |
| `target` | text | 0.0% | 4 |
| `target_type` | text | 0.0% | 1 |
| `status` | text | 0.0% | 1 |
| `summary` | jsonb | 0.0% | n/a |
| `error` | text | 100.0% | 0 |
| `purpose_note` | text | 100.0% | 0 |
| `started_at` | timestamp with time zone | 0.0% | 9 |
| `completed_at` | timestamp with time zone | 0.0% | 9 |
| `created_at` | timestamp with time zone | 0.0% | 9 |
| `updated_at` | timestamp with time zone | 0.0% | 9 |

## `dossier_audit_log` — 8 rows · 8 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 8 |
| `user_id` | text | 0.0% | 1 |
| `dossier_id` | uuid | 0.0% | 8 |
| `action` | text | 0.0% | 1 |
| `target` | text | 0.0% | 4 |
| `purpose_note` | text | 100.0% | 0 |
| `metadata` | jsonb | 0.0% | n/a |
| `created_at` | timestamp with time zone | 0.0% | 8 |

## `briefs` — 29 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 29 |
| `user_id` | uuid | 0.0% | 1 |
| `content` | text | 0.0% | 29 |
| `brief_date` | date | 0.0% | 29 |
| `generated_at` | timestamp with time zone | 0.0% | 29 |
| `articles_used` | integer | 0.0% | 5 |
| `model_used` | text | 0.0% | 1 |
| `source_counts` | jsonb | 13.8% | n/a |
| `evidence` | jsonb | 13.8% | n/a |

## `source_run_health` — 6 rows · 7 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `source_id` | text | 0.0% | 6 |
| `last_success_at` | timestamp with time zone | 83.3% | 1 |
| `last_failure_at` | timestamp with time zone | 16.7% | 5 |
| `last_failure` | text | 0.0% | 6 |
| `consecutive_failures` | integer | 0.0% | 6 |
| `rows_last_run` | integer | 0.0% | 1 |
| `updated_at` | timestamp with time zone | 0.0% | 6 |

## `coverage_panel_summaries` — 5 rows · 5 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `slug` | text | 0.0% | 5 |
| `summary` | text | 0.0% | 5 |
| `generated_at` | timestamp with time zone | 0.0% | 5 |
| `generated_by_model` | text | 0.0% | 1 |
| `source_sample_size` | integer | 0.0% | 3 |

## `users` — 3 rows · 4 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 3 |
| `email` | text | 0.0% | 3 |
| `created_at` | timestamp with time zone | 0.0% | 3 |
| `role` | text | 0.0% | 2 |

## `newsroom_broadcasts` — 2 rows · 10 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 2 |
| `channel_id` | uuid | 0.0% | 2 |
| `yt_video_id` | text | 0.0% | 2 |
| `title` | text | 0.0% | 2 |
| `title_en` | text | 100.0% | 0 |
| `started_at` | timestamp with time zone | 0.0% | 2 |
| `ended_at` | timestamp with time zone | 100.0% | 0 |
| `is_live` | boolean | 0.0% | 1 |
| `duration_sec` | integer | 100.0% | 0 |
| `created_at` | timestamp with time zone | 0.0% | 2 |

## `impersonation_sessions` — 25 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 25 |
| `admin_id` | uuid | 0.0% | 1 |
| `target_user_id` | uuid | 0.0% | 1 |
| `started_at` | timestamp with time zone | 0.0% | 25 |
| `ended_at` | timestamp with time zone | 4.0% | 24 |
| `reason` | text | 100.0% | 0 |

## `user_profiles` — 1 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 1 |
| `user_id` | uuid | 0.0% | 1 |
| `raw_description` | text | 0.0% | 1 |
| `role_type` | text | 0.0% | 1 |
| `organisation` | text | 100.0% | 0 |
| `geo_primary` | text | 0.0% | 1 |
| `geo_secondary` | ARRAY | 0.0% | n/a |
| `signal_priorities` | jsonb | 0.0% | n/a |
| `language_preferences` | ARRAY | 0.0% | n/a |
| `brief_time` | time without time zone | 0.0% | 1 |
| `brief_timezone` | text | 0.0% | 1 |
| `role_context` | text | 0.0% | 1 |
| `created_at` | timestamp with time zone | 0.0% | 1 |
| `updated_at` | timestamp with time zone | 0.0% | 1 |

## `district_geo_backfill_cursor` — 1 rows · 4 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `surface` | text | 0.0% | 1 |
| `last_processed` | uuid | 0.0% | 1 |
| `rows_done` | bigint | 0.0% | 1 |
| `updated_at` | timestamp with time zone | 0.0% | 1 |

## `entity_dict_meta` — 1 rows · 5 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | integer | 0.0% | 1 |
| `version` | integer | 0.0% | 1 |
| `last_updated_at` | timestamp with time zone | 0.0% | 1 |
| `entry_count` | integer | 0.0% | 1 |
| `updated_by` | text | 0.0% | 1 |

## `user_cards` — 6 rows · 13 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 6 |
| `user_id` | uuid | 0.0% | 1 |
| `label` | text | 0.0% | 6 |
| `definition_hash` | text | 0.0% | 6 |
| `entity_refs` | jsonb | 0.0% | n/a |
| `topic_filters` | jsonb | 0.0% | n/a |
| `geo_filter` | jsonb | 0.0% | n/a |
| `user_intent` | text | 0.0% | 6 |
| `created_at` | timestamp with time zone | 0.0% | 2 |
| `last_refreshed_at` | timestamp with time zone | 0.0% | 6 |
| `parent_card_id` | uuid | 16.7% | 1 |
| `sub_card_angle` | text | 16.7% | 5 |
| `sub_cards_spawned` | boolean | 0.0% | 1 |

## `kombu_queue` — 47 rows · 2 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | integer | 0.0% | 47 |
| `name` | character varying | 0.0% | 47 |

## `brief_quality_scores` — 24 rows · 19 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 24 |
| `user_id` | uuid | 0.0% | 1 |
| `brief_date` | date | 0.0% | 24 |
| `scored_at` | timestamp with time zone | 0.0% | 21 |
| `has_situation_status` | boolean | 0.0% | 1 |
| `has_key_developments` | boolean | 0.0% | 1 |
| `has_entities_today` | boolean | 0.0% | 1 |
| `has_signals_to_watch` | boolean | 0.0% | 1 |
| `has_financial_pulse` | boolean | 0.0% | 1 |
| `has_source_coverage` | boolean | 0.0% | 1 |
| `bracket_cites` | integer | 0.0% | 14 |
| `pillar_cites` | integer | 0.0% | 13 |
| `failure_marker_count` | integer | 0.0% | 1 |
| `invalid_indexes` | jsonb | 0.0% | n/a |
| `article_recency_avg_days` | numeric | 0.0% | 20 |
| `article_recency_max_days` | numeric | 0.0% | 7 |
| `articles_within_36h` | integer | 0.0% | 12 |
| `section_word_counts` | jsonb | 0.0% | n/a |
| `overall_score` | numeric | 0.0% | 21 |

## `newsroom_channel_live_digest` — 16 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `channel_id` | uuid | 0.0% | 16 |
| `video_id` | text | 0.0% | 16 |
| `caption_buffer` | text | 0.0% | 1 |
| `last_caption_at` | timestamp with time zone | 0.0% | 1 |
| `top_phrases` | jsonb | 0.0% | n/a |
| `top_stories` | jsonb | 0.0% | n/a |
| `summary` | text | 0.0% | 3 |
| `entity_ids` | ARRAY | 0.0% | n/a |
| `generated_at` | timestamp with time zone | 0.0% | 1 |

## `user_breaking_now` — 1 rows · 14 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `user_id` | uuid | 0.0% | 1 |
| `article_id` | uuid | 0.0% | 1 |
| `selected_at` | timestamp with time zone | 0.0% | 1 |
| `window_started_at` | timestamp with time zone | 0.0% | 1 |
| `source_tier` | smallint | 0.0% | 1 |
| `relevance_tier` | smallint | 0.0% | 1 |
| `candidates_count` | smallint | 0.0% | 1 |
| `near_dup_sources` | smallint | 0.0% | 1 |
| `decision_path` | text | 0.0% | 1 |
| `reason` | text | 0.0% | 1 |
| `picker_model` | text | 100.0% | 0 |
| `raw_pick_response` | jsonb | 100.0% | n/a |
| `headline_one_line` | text | 100.0% | 0 |
| `why_for_user` | text | 100.0% | 0 |

## `coverage_gaps_daily` — 40 rows · 8 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 40 |
| `detected_for_date` | date | 0.0% | 4 |
| `entity_id` | uuid | 0.0% | 15 |
| `social_volume_7d` | integer | 0.0% | 24 |
| `article_volume_7d` | integer | 0.0% | 2 |
| `ratio` | real | 0.0% | 24 |
| `summary` | text | 0.0% | 32 |
| `detected_at` | timestamp with time zone | 0.0% | 40 |

## `user_card_summaries` — 6 rows · 6 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `definition_hash` | text | 0.0% | 6 |
| `sections` | jsonb | 0.0% | n/a |
| `citations` | jsonb | 0.0% | n/a |
| `generated_at` | timestamp with time zone | 0.0% | 6 |
| `generated_by_model` | text | 0.0% | 1 |
| `sample_size` | integer | 0.0% | 3 |

## `article_contradictions` — 1 rows · 9 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 1 |
| `claim_a_id` | uuid | 0.0% | 1 |
| `claim_b_id` | uuid | 0.0% | 1 |
| `entity_id` | uuid | 0.0% | 1 |
| `divergence_summary` | text | 0.0% | 1 |
| `confidence` | real | 0.0% | 1 |
| `detected_at` | timestamp with time zone | 0.0% | 1 |
| `detected_by_model` | text | 0.0% | 1 |
| `is_resolved` | boolean | 0.0% | 1 |

## `newsroom_briefs` — 2 rows · 7 columns

| Column | Type | NULL% | Distinct |
|---|---|---:|---:|
| `id` | uuid | 0.0% | 2 |
| `for_date` | date | 0.0% | 2 |
| `generated_at` | timestamp with time zone | 0.0% | 2 |
| `stories` | jsonb | 0.0% | n/a |
| `story_count` | integer | 0.0% | 1 |
| `source_channel_count` | integer | 0.0% | 1 |
| `source_segment_count` | integer | 0.0% | 2 |
