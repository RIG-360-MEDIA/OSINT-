# Runbook: Bootstrapping the first super-admin

This is the single source of truth for setting up super-admin accounts on
a new RIG Surveillance deployment (dev, staging, or prod).

It replaces the hard-coded seed in
`scripts/migrations/030_rbac_and_impersonation.sql:65-68` (which is now
legacy — kept in migration history for the original developer's account
but no longer the recommended bootstrap path).

## TL;DR

1. Set `SUPER_ADMIN_EMAILS` in `infrastructure/.env`.
2. Sign up at `/signup` with each of those emails.
3. Restart the backend container.
4. Done — those accounts are now super-admins.

## Why an env var instead of a migration

The previous approach hard-coded the admin email in the migration SQL.
That was fine for the original developer's machine but unworkable for
any other deployment: a customer or operator would need to edit the
migration file, which means committing their email to git.

`SUPER_ADMIN_EMAILS` (read by `backend/auth/super_admin_seed.py` on every
boot) keeps the production secret out of source code while remaining
fully reproducible — the same docker image runs anywhere, only the
`.env` file changes.

## Step-by-step

### 1. Choose your admin email(s)

Pick at least **two** emails. Single-super-admin is a single point of
failure: if that account loses access (forgotten password, ex-employee,
locked-out inbox), no one else can promote anyone, and you'd have to
SSH into the database and run SQL by hand to recover.

Good choices:
- A personal address you trust
- A team alias (`ops@example.com`) for redundancy

### 2. Set the env var

In `infrastructure/.env`:

```env
SUPER_ADMIN_EMAILS=ops@example.com,backup@example.com
```

Comma-separated. Whitespace around commas is fine. Case-insensitive.

### 3. Sign up each account in Supabase

For each email:

1. Open the deployed frontend (e.g. `http://localhost:3000`)
2. Go to `/signup`
3. Enter the email and a password (≥6 characters)
4. Submit

Supabase creates the auth account with the password (hashed). The
backend's seed hook **does not** create auth accounts — it only flips
the role on accounts that already exist in Supabase. So this signup step
is mandatory.

If your Supabase project has email confirmation enabled, finish that too
before moving on.

### 4. Restart the backend

```bash
docker compose restart rig-backend
```

On boot, `backend/main.py:seed_admins_on_boot` runs the seed. It:

1. Reads `SUPER_ADMIN_EMAILS` from settings.
2. For each email, calls Supabase's admin API
   (`GET /auth/v1/admin/users?email=…`) using `SUPABASE_SERVICE_KEY` to
   resolve the auth user-id.
3. Upserts a `public.users` row with `role='super_admin'` for that id
   (`INSERT … ON CONFLICT (id) DO UPDATE SET role='super_admin'`).
4. Logs a summary: `{requested, promoted, already_admin, missing, skipped}`.

Tail the logs to confirm:

```bash
docker logs --tail 50 rig-backend | grep super-admin
```

You should see something like:

```
super-admin seed: promoted ops@example.com (uuid…) to super_admin
super-admin seed summary: {'requested': 2, 'promoted': 2, 'already_admin': 0, 'missing': 0, 'skipped': 0}
```

If you see `'missing': N`, that means N of those emails haven't signed
up at `/signup` yet. Do step 3 for them, then restart again.

### 5. Verify

Log in as one of the admin emails, navigate to `/admin`. You should see
the user-administration table.

Or, from the database:

```sql
SELECT email, role FROM users WHERE role = 'super_admin';
```

## Demoting a super-admin

The seed hook only promotes; it never demotes. To demote someone:

1. Remove their email from `SUPER_ADMIN_EMAILS` in `.env`.
2. Use the `/admin` UI's role dropdown to change them back to `user`,
   **or** run SQL directly:

   ```sql
   UPDATE users SET role = 'user' WHERE email = 'ex-admin@example.com';
   ```

Restarting after step 1 alone is **not** sufficient — the hook is
promote-only, so the role stays `super_admin` until step 2.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `super-admin seed: <email> not in Supabase yet` | Email missing in `auth.users` | Sign up at `/signup` with that exact email, then restart backend |
| `super-admin seed: SUPABASE_URL or SUPABASE_SERVICE_KEY missing` | Env vars not set | Check `.env` and restart |
| `super-admin seed: Supabase admin API returned 401` | `SUPABASE_SERVICE_KEY` is the wrong key (anon instead of service-role) | Get the service-role key from Supabase → Project Settings → API |
| `/admin` page shows "Super admin access required" after the above | Browser cached `/api/me/access` | Hard-refresh (Ctrl+Shift+R) |

## Why migration 030's hard-coded seed is still in git

Removing or rewriting an already-applied migration causes problems in
deployments that have already run it (the migration runner won't re-run
older migrations). The hard-coded `UPDATE` in 030 is now a no-op for any
new deployment whose target email differs from
`pranavsinghpuri09@gmail.com`, and harmless for the legacy one. Future
work could supersede it with a `031_remove_legacy_super_admin_seed.sql`
that resets the role for that specific email if no longer wanted.
