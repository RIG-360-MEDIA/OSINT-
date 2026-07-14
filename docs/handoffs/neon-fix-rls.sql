-- restore auth.uid() (exact box definition) + the 2 RLS policies that failed
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $fn$
  SELECT NULLIF(current_setting('app.user_id', true), '')::UUID
$fn$;
GRANT EXECUTE ON FUNCTION auth.uid() TO reader_ro, cms_rw;
DROP POLICY IF EXISTS users_own_history ON rigwire.user_reading_history;
DROP POLICY IF EXISTS users_own_prefs   ON rigwire.user_preferences;
CREATE POLICY users_own_history ON rigwire.user_reading_history USING ((user_id = auth.uid())) WITH CHECK ((user_id = auth.uid()));
CREATE POLICY users_own_prefs   ON rigwire.user_preferences   USING ((user_id = auth.uid())) WITH CHECK ((user_id = auth.uid()));
\echo === VERIFY ===
SELECT proname AS fn FROM pg_proc WHERE proname='uid';
SELECT tablename, policyname FROM pg_policies WHERE schemaname='rigwire' ORDER BY 1;
