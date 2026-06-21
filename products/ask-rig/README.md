# Ask-RIG

Read-only service that answers a natural-language question (English / Telugu / Hindi)
with a short, **cited** answer grounded only in the RIG corpus, plus the source
articles behind every claim. This is the Set-1 foundation (hybrid retrieval engine +
cited cross-lingual answer). See [SPEC.md](SPEC.md) and
[../../docs/research/feature-feasibility-and-set1.md](../../docs/research/feature-feasibility-and-set1.md).

## The read-only contract
- Connects as `analytics_user` with `default_transaction_read_only=on`. **SELECT only.**
- No write path to the corpus exists in this codebase. Any future per-user state goes
  in a **separate** app DB.
- Citations are validated server-side: every `[S#]` must resolve to a real retrieved
  doc or it's stripped and the answer is flagged `faithful=false`.

## Setup
```powershell
# 1. deps (LaBSE is heavy)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. config
copy .env.example .env
#    edit .env: set ASKRIG_DB_URL's password to analytics_user's
#    (from products/osint/backend/.env OSINT_DB_URL) and, to enable answers,
#    set ASKRIG_LLM_API_KEY (Groq by default).

# 3. open the read-only tunnel (separate terminal, keep running)
.\scripts\tunnel.ps1
```

## Pre-flight (do this first — it's the gate)
```powershell
.venv\Scripts\python scripts\verify_embedding.py
```
Confirms a freshly-embedded query lands in the v4 space: titles on-topic **and** an
English query surfacing Telugu/Hindi articles. If this looks wrong, stop — semantic
search is the foundation everything else sits on.

## Run
```powershell
.venv\Scripts\python -m uvicorn app.main:app --port 8010
# POST /ask
curl -s http://127.0.0.1:8010/ask -H "content-type: application/json" `
  -d '{"query":"What has Revanth Reddy said about farmer loan waivers?","top_k":8}'
# GET /health
```
Set `"answer": false` (or leave `ASKRIG_LLM_API_KEY` empty) to run **retrieval-only**
without an LLM key.

## Test
```powershell
.venv\Scripts\python -m pytest            # unit tests (no DB/model needed)
.venv\Scripts\python -m pytest -m integration   # live (needs tunnel + LaBSE)
```

## Eval (quality gate)
Build `eval/ground_truth.jsonl` by sampling story clusters (a cluster = a query +
its member article ids = the relevant set), then:
```powershell
.venv\Scripts\python eval\run_eval.py eval\ground_truth.jsonl
# gates: recall@10>=0.85  MRR>=0.6  xling_recall@10>=0.75
```

## Layout
`app/` config · db (read-only) · embedding (LaBSE) · retrieval (vector+fts+RRF) ·
llm · answer (cite-ID guardrail) · main (FastAPI). `eval/` offline metrics.
`scripts/` tunnel + embedding pre-flight. `tests/` unit + live integration.

## Deliberately deferred to later sets
Cross-pillar (clip/cutting) fusion — their vectors aren't in the v4 space; per-user
memory; live web; reranker; audio.
