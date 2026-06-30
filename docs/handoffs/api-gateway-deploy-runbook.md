# /v1 Client API Gateway — Deploy Runbook

The gateway lives in `products/osint/backend/v1/` and is wired into the
`osint-backend` container via one `install_v1(app)` call in `main.py`. It is
**fail-closed in production**: without `OSINT_APIKEY_HASH_SECRET` set it refuses
to authenticate any key (but the rest of the backend boots fine).

Deploy order matters. Do NOT issue a key before the secret + migration are in.

## 0. Pre-flight
- [ ] Code merged; `python -m pytest v1/tests` green.
- [ ] You have a super_user JWT (for the `/v1/admin/*` calls below).
- [ ] SSH to Hetzner: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`.

## 1. Set the key-hash secret (fail-closed gate)
Generate a strong secret and add it to the `osint-backend` environment
(compose env block for the service), then it must be present in the container:
```bash
openssl rand -hex 32          # use the output as the value
# add to infrastructure compose env for osint-backend:
#   OSINT_APIKEY_HASH_SECRET=<the hex>
```
> This secret keys the HMAC that hashes every API key. **If it ever changes,
> all existing keys stop validating** — treat it as permanent + back it up in
> the secret store. Never commit it.

## 2. Apply migration 117
```bash
docker cp scripts/migrations/117_api_gateway.sql rig-postgres:/tmp/117.sql
docker exec rig-postgres psql -U rig -d rig -f /tmp/117.sql
# verify:
docker exec rig-postgres psql -U rig -d rig -c "\dt analytics.api_*"
```
Creates `analytics.api_keys`, `org_api_scope`, `api_usage_events`,
`api_usage_counters`, `api_webhooks` + grants to `analytics_user`. Idempotent.

## 3. Deploy the code (baked container → docker cp + restart)
```bash
# from the repo's products/osint/backend:
docker cp v1 osint-backend:/app/v1
docker cp main.py osint-backend:/app/main.py
docker restart osint-backend
sleep 6 && docker ps --filter name=osint-backend --format '{{.Status}}'
```

## 4. Smoke test (no key needed)
```bash
curl -s https://desk.rig360media.com/v1/health    # -> {"data":{"status":"ok",...}}
```
If this 404s, the `/v1/*` path isn't routed to `osint-backend` — add a route in
`infrastructure/Caddyfile` (mirror the existing `/api/*` → osint-backend rule)
and `docker restart rig-caddy`.

## 5. Provision an org + issue a key (staff only)
```bash
SU="Authorization: Bearer <SUPER_USER_JWT>"
ORG=<org-uuid>

# (a) set the org's scope (the entities/topics/regions they may read)
curl -s -X PUT https://desk.rig360media.com/v1/admin/scope/$ORG \
  -H "$SU" -H 'Content-Type: application/json' \
  -d '{"all_entities":false,"entity_ids":["<entity-uuid>"],"regions":["IN"]}'

# (b) issue a key (returned ONCE)
curl -s -X POST https://desk.rig360media.com/v1/admin/keys \
  -H "$SU" -H 'Content-Type: application/json' \
  -d "{\"org_id\":\"$ORG\",\"label\":\"acme prod\",\"rate_limit_per_min\":120,\"monthly_quota\":50000}"
# -> {"data":{"key":"rig_live_…","warning":"Store this key now …"}}
```
Sandbox key: add `"sandbox":true` → returns a `rig_test_…` key.

## 6. Verify as the client
```bash
K="Authorization: Bearer rig_live_…"
curl -s https://desk.rig360media.com/v1/entities -H "$K"            # their entities
curl -s "https://desk.rig360media.com/v1/articles?window=7&limit=5" -H "$K"
curl -s https://desk.rig360media.com/v1/usage -H "$K"              # metering readback
curl -si https://desk.rig360media.com/v1/entities -H "$K" | grep -i x-ratelimit
```
Negative checks (should all be safe):
```bash
curl -s https://desk.rig360media.com/v1/entities                  # no key  -> 401
curl -s https://desk.rig360media.com/v1/entities -H "Authorization: Bearer rig_live_fake" # -> 401
curl -s https://desk.rig360media.com/v1/entities/<unscoped-entity-uuid> -H "$K"  # -> 404
```

## 7. Revoke
```bash
curl -s -X POST https://desk.rig360media.com/v1/admin/keys/<key-id>/revoke -H "$SU"
```
Revocation is immediate — the next request with that key gets 401.

## Rollback
- Code: re-`docker cp` the previous `main.py` (remove the `install_v1` block) +
  the previous `v1/` (or delete it) and restart. The migration is additive and
  safe to leave (no data path depends on it once the router is removed).
- The gateway is isolated: removing it cannot affect the JWT dashboard surface.

## Operational notes
- Rate limiting is **in-process** (single uvicorn worker). If `osint-backend`
  is ever scaled to multiple workers, move the bucket store to Redis.
- Webhook **delivery** is not yet implemented (storage only) — before enabling
  delivery, add SSRF protection (block private/loopback/link-local IPs) and a
  retry/backoff worker.
- `/v1/docs` (Swagger) and `/openapi.json` are FastAPI-generated; gate or
  expose per preference.

## Security review — fixed vs accepted
Independent adversarial review found **one** cross-tenant leak; all data paths
otherwise correctly scoped, no SQL injection, auth isolation confirmed.

**Fixed in this build:**
- **C-1** — `article_entities` now scope-filtered (was returning other orgs'
  provisioned entity ids/names on a shared article). Regression-tested.
- **H-6** — webhook signing secret is now *derived* from the webhook id, never
  stored in recoverable form (a DB read can't reveal it).
- **Misconfig fail-closed** — `OSINT_ENVIRONMENT` defaults to `production`, so a
  host that forgets the env var refuses the dev fallback secret rather than
  silently using a well-known key.

**Accepted / follow-up (not leaks — track before scale):**
- **H-3** quota check fails *open* on a counter-read DB error (availability over
  strict billing). Add an in-process fallback counter if quota must be hard.
- **H-4** `X-Forwarded-For` is client-spoofable for the audit-log IP — have
  Caddy strip client-set XFF and inject its own. Doesn't affect access control.
- **H-5** SSRF — the webhook **delivery worker isn't built**; before it ships it
  MUST block private/loopback/link-local IPs (resolve-then-check) and not follow
  redirects.
- **L-3** `api_usage_events` has no retention — add a monthly purge/partition.
