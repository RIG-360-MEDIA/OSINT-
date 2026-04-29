-- ============================================================================
-- 021_rbac_and_impersonation.sql
--
-- Adds role-based access control and super-admin impersonation:
--   1. users.role           — 'user' | 'super_admin'
--   2. user_page_access     — per-user page allowlist
--   3. impersonation_sessions — audit row per "view as" session
--   4. impersonation_actions  — per-request audit log inside a session
--   5. seeds super_admin role for pranavsinghpuri09@gmail.com (idempotent)
--   6. grants every existing user every non-admin page (idempotent)
--
-- Idempotent — safe to re-apply.
-- ============================================================================

-- 1. Role column on users
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user'
    CHECK (role IN ('user', 'super_admin'));

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);


-- 2. Per-user page access table
CREATE TABLE IF NOT EXISTS user_page_access (
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    page_slug  TEXT        NOT NULL,
    granted_by UUID        REFERENCES users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, page_slug)
);

CREATE INDEX IF NOT EXISTS idx_user_page_access_user ON user_page_access(user_id);


-- 3. Impersonation sessions (one row per "view as" session)
CREATE TABLE IF NOT EXISTS impersonation_sessions (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_user_id UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    reason         TEXT
);

CREATE INDEX IF NOT EXISTS idx_imp_sessions_admin  ON impersonation_sessions(admin_id);
CREATE INDEX IF NOT EXISTS idx_imp_sessions_target ON impersonation_sessions(target_user_id);
CREATE INDEX IF NOT EXISTS idx_imp_sessions_active ON impersonation_sessions(admin_id) WHERE ended_at IS NULL;


-- 4. Per-request audit log inside an impersonation session
CREATE TABLE IF NOT EXISTS impersonation_actions (
    id          BIGSERIAL    PRIMARY KEY,
    session_id  UUID         NOT NULL REFERENCES impersonation_sessions(id) ON DELETE CASCADE,
    method      TEXT         NOT NULL,
    path        TEXT         NOT NULL,
    status_code INT,
    at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_imp_actions_session ON impersonation_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_imp_actions_at      ON impersonation_actions(at);


-- 5. Seed super admin (idempotent — assumes Supabase signup has created the row)
UPDATE users
   SET role = 'super_admin'
 WHERE email = 'pranavsinghpuri09@gmail.com'
   AND role <> 'super_admin';


-- 6. Default page grants for every existing user (everything except admin).
--    New signups get the same default via the application-side hook in
--    /api/onboarding/confirm — this block only backfills existing rows.
INSERT INTO user_page_access (user_id, page_slug)
SELECT u.id, p.slug
  FROM users u
  CROSS JOIN (VALUES
      ('coverage'),
      ('clips'),
      ('cuttings'),
      ('threads'),
      ('signals'),
      ('documents'),
      ('brief'),
      ('analyst'),
      ('worldmonitor')
  ) AS p(slug)
ON CONFLICT (user_id, page_slug) DO NOTHING;
