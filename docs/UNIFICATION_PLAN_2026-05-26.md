# Branch Unification + Code Cleanup Plan

Goal: ONE unified branch, all security patches applied, code professionally formatted, no vulnerabilities, no dead code, tested, then pushed.

## Phase 1 — Safety net (10 min, ZERO risk)

```bash
cd /root/rig
# Snapshot current local state — preserves the 131 commits we've made
git branch local-snapshot-2026-05-26

# Verify database backup exists or create one
docker exec rig-postgres pg_dump -U rig -d rig | gzip > /tmp/rig-db-2026-05-26.sql.gz
ls -lh /tmp/rig-db-2026-05-26.sql.gz

# Stop any in-flight background scripts so they don't write to running code
docker exec rig-backend bash -c 'pkill -f "b1_b5|c1c2|d3d4|semantic_repass|b3_fix" 2>/dev/null; sleep 2'
```

## Phase 2 — Per-file decision matrix (30 min)

For each file that exists on BOTH sides, decide: keep origin / keep ours / merge both.

| File | Decision | Why |
|---|---|---|
| `backend/nlp/groq_client.py` | **Origin + my `_LOCAL_FAIL_COOLDOWN=0.0` patch re-applied** | Origin has Cerebras failover + token-bucket fixes, more mature |
| `backend/tasks/substrate/run_corpus_pass.py` | **Origin + my `extraction_version=3` stamp + canonical_url guard** | Origin's v3 prompt is May 17, newer |
| `backend/tasks/coverage/claims_quotes_task.py` | **Origin + ::text casts + B2 English skip + entity alias resolver** | Origin's base, my fixes on top |
| `backend/celery_app.py` | **Origin + newsroom imports + weekly v3 schedule** | Origin's structure, my additions |
| `backend/routers/brief_router.py` | **MINE wins** | Origin has the auth-gated version, we need the public KPI/entities/emerging/stories endpoints |
| `backend/observability/brief_*.py` | **MINE — entirely new files I wrote today** | Not on origin |
| `backend/main.py` | Origin | Origin has cleaner router registration |
| `frontend/src/components/coverage/*` | Origin (May 17 editorial-layout) | Newer, more polished |
| `package.json` / `requirements.txt` | **Origin** | Has 33 CVE patches — must take |
| `infrastructure/docker-compose.yml` | Compare 1-line each | Probably origin |

## Phase 3 — Reset + cherry-pick (1-2 hours)

```bash
# Fetch origin state
git fetch origin --tags

# Reset local to origin's tip (gets all 74 origin commits including CVE patches + docs)
git reset --hard origin/fix/brief-prod-readiness

# Now cherry-pick our 9 today's-session commits back on top
git cherry-pick 56e1ebd  # observe v2
git cherry-pick ce569c4  # pool + clustering
git cherry-pick c862c07  # newsroom
git cherry-pick 2f6b146  # today's data quality sprint  ← biggest, expect conflicts
git cherry-pick f7769b9  # misc
git cherry-pick 5b1fbbc  # substrate pipeline
git cherry-pick 431c4f0  # migrations 063-068
git cherry-pick 2f36af6  # observe page
git cherry-pick 5f7bbb8  # v3_upgrade task + scripts

# For EACH conflict that arises:
#   1. Open the file
#   2. Decide per the matrix in Phase 2
#   3. git add <file>
#   4. git cherry-pick --continue
```

Some cherry-picks may NOT apply (because origin already has equivalent commits). Skip those: `git cherry-pick --skip`.

## Phase 4 — Code quality pass (1-2 hours)

```bash
# Remove all .bak files anywhere
find /root/rig -name '*.bak*' -delete
find /root/rig -name '__pycache__' -type d -exec rm -rf {} +

# Format Python with black (per Python coding-style.md)
docker exec rig-backend bash -c '
  pip install -q black ruff isort
  black /app/backend
  isort /app/backend
  ruff check /app/backend --fix
'

# Format frontend with prettier
cd /root/rig/frontend && npx prettier --write 'src/**/*.{ts,tsx,js,jsx,css}'

# Find dead imports
docker exec rig-backend bash -c '
  pip install -q vulture
  vulture /app/backend --min-confidence 80 | head -n 50
'

# Find dead code patterns
grep -rn "TODO\|FIXME\|XXX\|HACK" /root/rig/backend --include="*.py" | head -n 20
```

## Phase 5 — Security audit (30 min)

```bash
# Backend Python vulnerabilities
docker exec rig-backend bash -c 'pip install -q pip-audit && pip-audit'

# Frontend npm vulnerabilities
cd /root/rig/frontend && npm audit --omit=dev

# Static security analysis with bandit (per Python security.md)
docker exec rig-backend bash -c 'pip install -q bandit && bandit -r /app/backend -ll'

# Check for hardcoded secrets
docker exec rig-backend bash -c '
  pip install -q detect-secrets
  detect-secrets scan /app/backend
'
```

## Phase 6 — Test pass (30-60 min)

```bash
# Backend pytest
docker exec rig-backend bash -c '
  cd /app && pip install -q pytest pytest-asyncio pytest-cov
  pytest backend/tests -x --tb=short 2>&1 | tail -n 40
'

# Frontend vitest
cd /root/rig/frontend && npm run test -- --run 2>&1 | tail -n 30

# Smoke-test brief endpoints
for ep in kpi entities emerging stories; do
  echo "=== $ep ==="
  curl -s --max-time 5 https://robin-osi.rig360media.com/api/brief/$ep | head -c 200
  echo ""
done

# Verify celery workers boot
docker exec rig-backend bash -c '
  ps -ef | grep "[c]elery worker" | wc -l
  celery -A backend.celery_app inspect ping -t 3
'
```

## Phase 7 — Production verification (30 min)

```bash
# Rebuild docker image with unified code
cd /root/rig/infrastructure
docker compose --env-file .env.prod -f docker-compose.prod.yml build rig-backend

# Recreate container
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --no-deps --force-recreate rig-backend

# Wait for ready
for i in {1..20}; do
  curl -s --max-time 2 http://127.0.0.1:8000/docs >/dev/null && echo ready && break
  sleep 2
done

# Watch logs for errors in first 60s
docker logs rig-backend --since=60s 2>&1 | grep -iE "error|exception|critical" | head -n 30
```

## Phase 8 — Push (5 min)

```bash
# Force-with-lease is safer than --force; refuses if remote moved
git push --force-with-lease origin fix/brief-prod-readiness

# Verify on GitHub
git log origin/fix/brief-prod-readiness -5 --oneline
```

## Total time estimate
| Phase | Time |
|---|---|
| Safety net | 10 min |
| Decision matrix | 30 min |
| Reset + cherry-pick + conflict resolution | 1-2 hours |
| Code quality pass | 1-2 hours |
| Security audit | 30 min |
| Test pass | 30-60 min |
| Production verification | 30 min |
| Push | 5 min |
| **Total** | **~4-6 hours** |

## Risk assessment

| Risk | Mitigation |
|---|---|
| Reset wipes our work | Phase 1 safety branch preserves all 131 commits |
| Cherry-pick conflicts misresolved | Test pass in Phase 6 catches semantic bugs |
| Production breaks after push | Phase 7 verifies before push; can roll back to safety branch |
| Database affected | **Database is NEVER touched in any phase** |

## Rollback plan (if it goes wrong)

```bash
# Revert to safety state
git reset --hard local-snapshot-2026-05-26
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --no-deps --force-recreate rig-backend
# DB unchanged regardless
```
