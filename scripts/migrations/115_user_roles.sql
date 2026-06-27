-- Migration 115: per-user role column for night-desk access control.
--
-- Three tiers:
--   super_user  — can see all users, impersonate any user, has admin access
--   admin       — full page access including RAG chat (Ask)
--   client      — same as admin EXCEPT no Ask / RAG pages
--
-- Existing super_admins get super_user role automatically.
-- Default for all new users is 'client' (least privilege).

ALTER TABLE analytics.users
  ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'client'
    CONSTRAINT users_role_check CHECK (role IN ('super_user', 'admin', 'client'));

-- Existing super-admins become super_user
UPDATE analytics.users SET role = 'super_user' WHERE is_super_admin = TRUE AND role = 'client';

-- Index for admin user-list queries
CREATE INDEX IF NOT EXISTS idx_analytics_users_role ON analytics.users (role);
