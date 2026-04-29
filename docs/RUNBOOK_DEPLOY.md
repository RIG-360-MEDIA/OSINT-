# Production Deploy Runbook

Operator-facing checklist for taking RIG Surveillance from a green local
build to a public production deployment. Code-side production-readiness
work is complete (see `docs/qa/auth-rbac-defects.md`); the items below
are the things only you (the operator) can do.

---

## 🔴 Must-do before going live

### 1. Fix the `/brief` Suspense wrap (build-time blocker)

`npm run build` currently fails at the static prerender step for
`/brief` because the page calls `useSearchParams()` outside a
`<Suspense>` boundary. I shipped the equivalent fix for
`/worldmonitor/page.tsx` — same pattern applies to `/brief/page.tsx`:

```tsx
// Wrap the inner body in <Suspense>:
import { Suspense } from 'react'

function BriefBody() {
  // existing code that calls useSearchParams() goes here
}

export default function BriefPage() {
  return (
    <Suspense fallback={null}>
      <BriefBody />
    </Suspense>
  )
}
```

Owner: the concurrent "brief production-readiness" session. Confirm with
them or fold the fix in yourself before deploying.

### 2. Production `.env`

Copy `infrastructure/.env.example` to `infrastructure/.env` and fill in
**real** values:

```env
# Required — backend refuses to start without these
DATABASE_URL=postgresql+asyncpg://rig:STRONG_PASSWORD@rig-postgres:5432/rig
DATABASE_URL_SYNC=postgresql://rig:STRONG_PASSWORD@rig-postgres:5432/rig
POSTGRES_PASSWORD=STRONG_PASSWORD
GROQ_API_KEYS=gsk_real_key_1,gsk_real_key_2

# Required — Supabase auth + JWT
SUPABASE_URL=https://your-real-project.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_...                  # service-role key
SUPABASE_ANON_KEY=sb_publishable_...                # anon (publishable) key
SUPABASE_JWT_SECRET=hs256_secret_from_supabase_settings_api_jwt_secret
NEXT_PUBLIC_SUPABASE_URL=https://your-real-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_...

# Required — production mode
ENVIRONMENT=production                              # CRITICAL — JWT verification fails closed
NEXT_PUBLIC_API_URL=https://api.your-domain.com     # not localhost

# Required — admin bootstrap (recommend 2+ for redundancy)
SUPER_ADMIN_EMAILS=ops@your-domain.com,backup@your-domain.com

# Strongly recommended
RIG_CORS_ORIGINS=https://app.your-domain.com        # exact frontend origin

# Optional — leave empty to skip features
NEWSDATA_API_KEY=
YOUTUBE_API_KEY=
TELEGRAM_BOT_TOKEN=
ACLED_ACCESS_TOKEN=
# ... see .env.example for the full list
```

Key points:
- `ENVIRONMENT=production` is the difference between dev (skips JWT
  signature verification when the secret is empty) and prod (refuses
  every request with 500 if the secret is empty). Get this wrong and
  either auth is broken (no secret + prod) or auth is bypassed (no
  secret + dev).
- `SUPER_ADMIN_EMAILS` is read on every backend boot. Sign up with each
  email at `/signup` first; the seed hook then auto-promotes.
- See `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` for the admin bootstrap
  details.

### 3. SSL / TLS termination

Supabase JWTs sit in browser localStorage. Over plain HTTP they are
trivially stolen by any wifi sniffer or compromised intermediate. You
**must** terminate TLS at your edge:

- **Vercel / Render / Fly / Railway**: TLS is automatic.
- **Cloudflare in front of self-host**: enable "Full (strict)" SSL mode
  and a Cloudflare-managed cert.
- **Self-hosted nginx / Caddy / Traefik**: use Let's Encrypt
  (`certbot` or Caddy's built-in ACME). Sample Caddy block:

  ```
  app.your-domain.com {
      reverse_proxy rig-frontend:3000
  }
  api.your-domain.com {
      reverse_proxy rig-backend:8000
  }
  ```

After deploy, confirm by visiting `https://app.your-domain.com` and
checking the lock icon shows a valid cert.

### 4. Database backups

The Postgres data lives in the `pgdata` Docker volume. Without backups,
one disk failure = total data loss.

Pick one:

- **Hosted Postgres** — migrate to Supabase Postgres / Neon / AWS RDS,
  which give you point-in-time recovery for free. Easiest. Requires
  setting `DATABASE_URL` to the hosted DSN and re-running migrations.
- **Self-hosted with `pg_dump` cron** — daily dump to S3 / Backblaze:

  ```bash
  # /etc/cron.daily/rig-pgbackup
  TS=$(date -u +%Y%m%d-%H%M%S)
  docker exec rig-postgres pg_dump -U rig rig | gzip > /backups/rig-${TS}.sql.gz
  aws s3 cp /backups/rig-${TS}.sql.gz s3://your-bucket/db/
  find /backups -mtime +7 -delete
  ```

  Test the restore at least once before relying on it.

### 5. Sign up the admin email(s) on the prod Supabase project

The seed hook only flips role; it does not create auth accounts. For
each email in `SUPER_ADMIN_EMAILS`:

1. Visit `https://app.your-domain.com/signup`
2. Sign up with that exact email + a strong password (≥6 chars)
3. If the prod Supabase project has email confirmation enabled, click
   the confirm link in your inbox

Then `docker compose restart rig-backend` (or your equivalent) so the
seed hook resolves the email → Supabase user id → flips role to
`super_admin`. Confirm with:

```bash
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT email, role FROM users WHERE role='super_admin';"
```

### 6. Confirm migrations apply on first prod boot

The Dockerfile is set up to run `scripts/migrations/*.sql` on first
boot. After your first prod `docker compose up`, verify all 36
migrations are present:

```bash
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT count(*) FROM information_schema.tables
   WHERE table_schema = 'public';"
# expect at least 25–30 tables (users, articles, briefs, user_page_access, ...)
```

If migrations didn't run, manually:

```bash
for f in scripts/migrations/*.sql; do
    docker exec -i rig-postgres psql -U rig -d rig < "$f"
done
```

---

## 🟡 Strongly recommended

### 7. Error monitoring (Sentry / Better Stack / similar)

Pick one. Without monitoring, you find out about errors when a user
complains.

For Sentry on the backend, add to `backend/main.py`:

```python
import sentry_sdk
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN", ""), traces_sample_rate=0.1)
```

And to the frontend, follow Sentry's Next.js setup wizard (`npx
@sentry/wizard@latest -i nextjs`).

### 8. Email confirmation in Supabase project settings

Decide whether new users must confirm their email before they can log
in. In Supabase project → Authentication → Providers → Email →
"Confirm email" toggle. If on, signups can't log in until they click
the email link, which prevents drive-by signups using fake addresses.

### 9. Set CORS allow-list explicitly

Backend reads `RIG_CORS_ORIGINS` (comma-separated) — a wide allow-list
defaults to localhost. Pin it to your real frontend origin:

```env
RIG_CORS_ORIGINS=https://app.your-domain.com
```

### 10. Reverse-proxy rate limits / WAF

The in-process limiter (`backend/rate_limiter.py`) protects LLM and
admin endpoints, but it's per-container and doesn't cover overall
traffic shape. A reverse-proxy or WAF in front (Cloudflare, AWS WAF,
nginx `limit_req_zone`) handles brute-force, scrape attacks, etc.

---

## 🟢 Nice-to-have (post-launch)

- **D-08** — display_name is collected in signup but never persisted
  (cosmetic, not functional).
- **Frontend `npm run build` warnings** — there's a webpack warning
  about big string serialization (215 kiB). Cosmetic, not a blocker.
- **Restrict super_admin nav to /admin only when not impersonating** —
  cosmetic UX cleanup; you confirmed your workflow doesn't need it.
- **Concurrent brief session items** — the `/brief` Suspense wrap (must
  fix #1 above), `/brief/generate` rate limit (D-06 deferred portion).

---

## Pre-launch checklist (paste this into a GitHub issue)

- [ ] Brief Suspense wrap shipped (build passes `npm run build`)
- [ ] Production `infrastructure/.env` filled in with real values
- [ ] `ENVIRONMENT=production`
- [ ] `SUPABASE_JWT_SECRET` set (real secret from Supabase dashboard)
- [ ] `SUPER_ADMIN_EMAILS` lists at least 2 emails
- [ ] DNS pointing to deployment
- [ ] TLS terminating in front of frontend & backend (lock icon
      green in browser)
- [ ] DB backups configured + at least one restore tested
- [ ] Each admin email has signed up at `/signup` + `restart rig-backend`
      → seed hook log shows `'promoted': N` or `'already_admin': N`
- [ ] `docker exec rig-postgres psql -U rig -d rig -c "SELECT email,
      role FROM users WHERE role='super_admin';"` returns expected rows
- [ ] Sentry / monitoring receiving heartbeat
- [ ] CORS origin pinned to prod frontend domain
- [ ] One full E2E happy-path: signup → onboarding → brief renders
- [ ] One full admin-flow E2E: log in as admin → /admin → "View as" →
      target user's brief renders → Exit → admin's /admin restored
