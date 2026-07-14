-- ===================================================================
-- Neon Phase 1 — auth.users + rigwire schema + least-priv roles
-- Run this whole file in Neon (SQL Editor) OR let it be applied via psql.
-- Set the two role passwords before running (search CHANGE_ME).
-- ===================================================================
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (
  id uuid PRIMARY KEY,
  email text,
  password_hash text,
  email_verified_at timestamptz,
  display_name text,
  role text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- ===== your real rigwire schema (9 tables) =====
--
-- PostgreSQL database dump
--

-- Dumped from database version 15.4 (Debian 15.4-2.pgdg120+1)
-- Dumped by pg_dump version 15.4 (Debian 15.4-2.pgdg120+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: rigwire; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA rigwire;


--
-- Name: SCHEMA rigwire; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA rigwire IS 'Rig Wire per-user content: preferences, reading history, audit log. Owned by rigwire_app.';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: dedup_decisions_log; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.dedup_decisions_log (
    id bigint NOT NULL,
    user_id uuid,
    article_id uuid NOT NULL,
    decision text NOT NULL,
    score numeric(4,3),
    canonical_id uuid,
    model_version text DEFAULT 'v4-trgm-0.55'::text NOT NULL,
    decided_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dedup_decisions_log_id_seq; Type: SEQUENCE; Schema: rigwire; Owner: -
--

CREATE SEQUENCE rigwire.dedup_decisions_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dedup_decisions_log_id_seq; Type: SEQUENCE OWNED BY; Schema: rigwire; Owner: -
--

ALTER SEQUENCE rigwire.dedup_decisions_log_id_seq OWNED BY rigwire.dedup_decisions_log.id;


--
-- Name: editorial_audit; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.editorial_audit (
    id bigint NOT NULL,
    story_id uuid,
    editor_id text DEFAULT 'system'::text NOT NULL,
    action text NOT NULL,
    before jsonb,
    after jsonb,
    at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: editorial_audit_id_seq; Type: SEQUENCE; Schema: rigwire; Owner: -
--

CREATE SEQUENCE rigwire.editorial_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: editorial_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: rigwire; Owner: -
--

ALTER SEQUENCE rigwire.editorial_audit_id_seq OWNED BY rigwire.editorial_audit.id;


--
-- Name: editorial_overrides; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.editorial_overrides (
    story_id uuid NOT NULL,
    action text DEFAULT 'live'::text NOT NULL,
    pinned_rank integer,
    importance_delta numeric DEFAULT 0 NOT NULL,
    section_override text,
    human_locked boolean DEFAULT false NOT NULL,
    edited_headline text,
    edited_dek text,
    edited_body text,
    edited_tags text[],
    editor_id text DEFAULT 'system'::text NOT NULL,
    reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    edited_image text,
    CONSTRAINT editorial_overrides_action_check CHECK ((action = ANY (ARRAY['live'::text, 'killed'::text, 'pinned'::text, 'held'::text])))
);


--
-- Name: image_checks; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.image_checks (
    thumbnail_url text NOT NULL,
    clean boolean NOT NULL,
    has_text boolean,
    detail text,
    checked_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: manual_stories; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.manual_stories (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    headline text NOT NULL,
    dek text,
    body text NOT NULL,
    topic text DEFAULT 'OTHER'::text NOT NULL,
    country text,
    image_url text,
    status text DEFAULT 'PUBLISHABLE'::text NOT NULL,
    importance numeric DEFAULT 40 NOT NULL,
    editor_id text DEFAULT 'system'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: onboarding_seed_articles; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.onboarding_seed_articles (
    id text NOT NULL,
    headline text NOT NULL,
    dek text NOT NULL,
    source_label text NOT NULL,
    topic_key text NOT NULL,
    length_bucket text NOT NULL,
    region_code text NOT NULL,
    time_horizon text NOT NULL,
    tone text NOT NULL,
    display_order integer NOT NULL,
    body_excerpt text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT onboarding_seed_articles_length_bucket_check CHECK ((length_bucket = ANY (ARRAY['flash'::text, 'worldwide'::text]))),
    CONSTRAINT onboarding_seed_articles_time_horizon_check CHECK ((time_horizon = ANY (ARRAY['breaking'::text, 'aftermath'::text, 'evergreen'::text]))),
    CONSTRAINT onboarding_seed_articles_tone_check CHECK ((tone = ANY (ARRAY['analytical'::text, 'human_interest'::text, 'numbers_heavy'::text, 'explainer'::text, 'literary'::text, 'profile'::text])))
);


--
-- Name: ranking_weights; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.ranking_weights (
    id integer DEFAULT 1 NOT NULL,
    topic_weights jsonb DEFAULT '{}'::jsonb NOT NULL,
    country_weights jsonb DEFAULT '{}'::jsonb NOT NULL,
    recency_halflife_h numeric DEFAULT 12 NOT NULL,
    source_weight numeric DEFAULT 1.0 NOT NULL,
    velocity_weight numeric DEFAULT 1.0 NOT NULL,
    updated_by text DEFAULT 'system'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ranking_weights_id_check CHECK ((id = 1))
);


--
-- Name: user_preferences; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.user_preferences (
    user_id uuid NOT NULL,
    topics text[] DEFAULT '{}'::text[] NOT NULL,
    reader_intents text[] DEFAULT '{}'::text[] NOT NULL,
    delivery_window text,
    delivery_frequency text,
    seed_picks text[] DEFAULT '{}'::text[] NOT NULL,
    seed_skipped text[] DEFAULT '{}'::text[] NOT NULL,
    primary_region text,
    secondary_regions text[] DEFAULT '{}'::text[] NOT NULL,
    voice_preference text,
    signup_intent text,
    locale text DEFAULT 'en'::text NOT NULL,
    timezone text DEFAULT 'UTC'::text NOT NULL,
    onboarded_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_preferences_complete_when_onboarded CHECK (((onboarded_at IS NULL) OR ((primary_region IS NOT NULL) AND (delivery_window IS NOT NULL) AND (delivery_frequency IS NOT NULL) AND (voice_preference IS NOT NULL) AND (signup_intent IS NOT NULL) AND (array_length(topics, 1) >= 3) AND (array_length(seed_picks, 1) = 5)))),
    CONSTRAINT user_preferences_delivery_frequency_check CHECK ((delivery_frequency = ANY (ARRAY['daily_only'::text, 'daily_plus_breaking'::text, 'breaking_only'::text, 'web_only'::text]))),
    CONSTRAINT user_preferences_delivery_window_check CHECK ((delivery_window = ANY (ARRAY['morning'::text, 'lunch'::text, 'evening'::text, 'bedtime'::text]))),
    CONSTRAINT user_preferences_reader_intents_check CHECK ((reader_intents <@ ARRAY['quick_morning'::text, 'deep_read'::text, 'breaking_only'::text, 'across_sides'::text, 'weekend_reader'::text])),
    CONSTRAINT user_preferences_signup_intent_check CHECK ((signup_intent = ANY (ARRAY['better_habit'::text, 'less_doomscroll'::text, 'follow_stories'::text, 'no_slant'::text, 'curious'::text]))),
    CONSTRAINT user_preferences_voice_preference_check CHECK ((voice_preference = ANY (ARRAY['wire'::text, 'newsroom'::text, 'magazine'::text, 'briefing'::text, 'voice'::text])))
);

ALTER TABLE ONLY rigwire.user_preferences FORCE ROW LEVEL SECURITY;


--
-- Name: user_reading_history; Type: TABLE; Schema: rigwire; Owner: -
--

CREATE TABLE rigwire.user_reading_history (
    user_id uuid NOT NULL,
    article_id uuid NOT NULL,
    mode text NOT NULL,
    shown_at timestamp with time zone DEFAULT now() NOT NULL,
    dwell_ms integer,
    completed boolean DEFAULT false NOT NULL
);

ALTER TABLE ONLY rigwire.user_reading_history FORCE ROW LEVEL SECURITY;


--
-- Name: dedup_decisions_log id; Type: DEFAULT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.dedup_decisions_log ALTER COLUMN id SET DEFAULT nextval('rigwire.dedup_decisions_log_id_seq'::regclass);


--
-- Name: editorial_audit id; Type: DEFAULT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.editorial_audit ALTER COLUMN id SET DEFAULT nextval('rigwire.editorial_audit_id_seq'::regclass);


--
-- Name: dedup_decisions_log dedup_decisions_log_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.dedup_decisions_log
    ADD CONSTRAINT dedup_decisions_log_pkey PRIMARY KEY (id);


--
-- Name: editorial_audit editorial_audit_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.editorial_audit
    ADD CONSTRAINT editorial_audit_pkey PRIMARY KEY (id);


--
-- Name: editorial_overrides editorial_overrides_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.editorial_overrides
    ADD CONSTRAINT editorial_overrides_pkey PRIMARY KEY (story_id);


--
-- Name: image_checks image_checks_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.image_checks
    ADD CONSTRAINT image_checks_pkey PRIMARY KEY (thumbnail_url);


--
-- Name: manual_stories manual_stories_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.manual_stories
    ADD CONSTRAINT manual_stories_pkey PRIMARY KEY (id);


--
-- Name: onboarding_seed_articles onboarding_seed_articles_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.onboarding_seed_articles
    ADD CONSTRAINT onboarding_seed_articles_pkey PRIMARY KEY (id);


--
-- Name: ranking_weights ranking_weights_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.ranking_weights
    ADD CONSTRAINT ranking_weights_pkey PRIMARY KEY (id);


--
-- Name: user_preferences user_preferences_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.user_preferences
    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id);


--
-- Name: user_reading_history user_reading_history_pkey; Type: CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.user_reading_history
    ADD CONSTRAINT user_reading_history_pkey PRIMARY KEY (user_id, article_id, mode);


--
-- Name: dedup_log_user_time_idx; Type: INDEX; Schema: rigwire; Owner: -
--

CREATE INDEX dedup_log_user_time_idx ON rigwire.dedup_decisions_log USING btree (user_id, decided_at DESC);


--
-- Name: editorial_audit_at_idx; Type: INDEX; Schema: rigwire; Owner: -
--

CREATE INDEX editorial_audit_at_idx ON rigwire.editorial_audit USING btree (at DESC);


--
-- Name: editorial_audit_story_idx; Type: INDEX; Schema: rigwire; Owner: -
--

CREATE INDEX editorial_audit_story_idx ON rigwire.editorial_audit USING btree (story_id);


--
-- Name: reading_history_user_time_idx; Type: INDEX; Schema: rigwire; Owner: -
--

CREATE INDEX reading_history_user_time_idx ON rigwire.user_reading_history USING btree (user_id, shown_at DESC);


--
-- Name: dedup_decisions_log dedup_decisions_log_user_id_fkey; Type: FK CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.dedup_decisions_log
    ADD CONSTRAINT dedup_decisions_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id);


--
-- Name: user_preferences user_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.user_preferences
    ADD CONSTRAINT user_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: user_reading_history user_reading_history_user_id_fkey; Type: FK CONSTRAINT; Schema: rigwire; Owner: -
--

ALTER TABLE ONLY rigwire.user_reading_history
    ADD CONSTRAINT user_reading_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: user_preferences; Type: ROW SECURITY; Schema: rigwire; Owner: -
--

ALTER TABLE rigwire.user_preferences ENABLE ROW LEVEL SECURITY;

--
-- Name: user_reading_history; Type: ROW SECURITY; Schema: rigwire; Owner: -
--

ALTER TABLE rigwire.user_reading_history ENABLE ROW LEVEL SECURITY;

--
-- Name: user_reading_history users_own_history; Type: POLICY; Schema: rigwire; Owner: -
--

CREATE POLICY users_own_history ON rigwire.user_reading_history USING ((user_id = auth.uid())) WITH CHECK ((user_id = auth.uid()));


--
-- Name: user_preferences users_own_prefs; Type: POLICY; Schema: rigwire; Owner: -
--

CREATE POLICY users_own_prefs ON rigwire.user_preferences USING ((user_id = auth.uid())) WITH CHECK ((user_id = auth.uid()));


--
-- PostgreSQL database dump complete
--


-- ===== least-priv roles for Vercel =====
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='reader_ro') THEN CREATE ROLE reader_ro LOGIN PASSWORD 'CHANGE_ME_READ'; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='cms_rw')    THEN CREATE ROLE cms_rw    LOGIN PASSWORD 'CHANGE_ME_WRITE'; END IF;
END $$;
GRANT USAGE ON SCHEMA rigwire, auth TO reader_ro, cms_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA rigwire TO reader_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rigwire TO cms_rw;
GRANT SELECT ON auth.users TO reader_ro, cms_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rigwire TO cms_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA rigwire GRANT SELECT ON TABLES TO reader_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA rigwire GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO cms_rw;
