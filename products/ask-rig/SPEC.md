# Ask-RIG — Spec (V1, the Set-1 foundation)

**One line:** a read-only service that answers a natural-language question (EN/TE/HI)
with a short, **cited** answer grounded *only* in the RIG corpus, and returns the
source articles behind every claim.

This is feature **0+1** of Set 1: the hybrid retrieval engine *plus* the cited
cross-lingual answer surface. Every later feature (entity feed, framing contrast,
dedup, brief) reuses this engine.

## Hard contract (non-negotiable)
- **READ-ONLY.** Connects as `analytics_user` with `default_transaction_read_only=on`.
  SELECT only. The app exposes **no** write path to the corpus. Any future per-user
  state (history, saved searches) goes in a **separate** app DB — never here.
- **No fabricated citations.** Every `[S#]` the LLM emits must resolve to a real
  retrieved doc, validated before the response leaves the server.
- **Honest refusal.** If retrieval is empty or the model can't ground an answer,
  it says so — it does not improvise from outside knowledge.

## Architecture (V1)
```
POST /ask {query, top_k, languages?, answer?}
        │
        ▼
  embed query  ──► LaBSE (sentence-transformers/LaBSE)  → 768-d vector
        │           (same model family as articles.labse_embedding_v4)
        ▼
  hybrid retrieval (READ-ONLY SELECTs on `articles`)
    ├─ semantic:  ORDER BY labse_embedding_v4 <=> qvec     (HNSW)   → top k_vec
    └─ lexical:   fts @@ websearch_to_tsquery(...)         (GIN)    → top k_lex
        │
        ▼  Reciprocal Rank Fusion (k=60) → top_k docs
        ▼
  answer (optional) ──► LLM (OpenAI-compatible; Groq default)
        │   strict prompt: answer ONLY from sources, cite [S#] each claim
        ▼
  cite-ID guardrail: drop/flag any [S#] not in the doc set; mark `faithful`
        ▼
AskResponse {answer, faithful, citations[], retrieved[], notes}
```

## Data it uses (verified live, 2026-06-19)
- `articles.labse_embedding_v4` — canonical vector (recipe `v4-tr-title-1024`), 94%+.
  **Not** legacy `labse_embedding` (recipe-mixed).
- `articles.fts` — tsvector, **100% populated** → lexical leg needs no new extension.
- Filter to the clean set: `substrate_status='ok' AND NOT is_duplicate` (~ usable corpus).
- English-facing text: `title` + `lead_text_translated` (97%); **not** `full_text_translated` (17%).

## Components (one small module each)
| File | Responsibility |
|---|---|
| `app/config.py` | `ASKRIG_*` settings (frozen dataclass) |
| `app/db.py` | async read-only engine + `ping()`; no writes |
| `app/embedding.py` | LaBSE query embedder + `to_pgvector()` |
| `app/retrieval.py` | vector + lexical SQL, `reciprocal_rank_fusion()` (pure) |
| `app/llm.py` | OpenAI-compatible provider (Groq default), pluggable |
| `app/answer.py` | prompt build + **cite-ID guardrail** (pure, tested) |
| `app/schemas.py` | pydantic request/response |
| `app/main.py` | FastAPI `/ask`, `/health` |
| `eval/run_eval.py` | recall@k, MRR, cross-lingual subset |
| `scripts/verify_embedding.py` | **pre-flight**: query↔v4 space compatibility |

## API
`POST /ask` → body `{query: str, top_k?: int=8, languages?: [str], answer?: bool=true}`
→ `{query, answer: str|null, faithful: bool, citations: [{marker,doc_id,title,url,...}], retrieved: [RetrievedDoc], notes}`.
`GET /health` → DB reachable + read-only.

## Eval gates (V1 is "great" only when ALL pass — Aryan's rule)
Build a ground-truth set first (sample story clusters → a cluster = relevant set):
1. **Recall@10 ≥ 0.85**, MRR ≥ 0.6 on the labeled set.
2. **Cross-lingual**: EN query, recall@10 ≥ 0.75 on TE/HI relevant docs.
3. **Faithfulness**: 100% of `[S#]` resolve to real docs; 0 invented citations on 30 Q&A.
4. Reranker (bge) only added if it lifts nDCG ≥ +10% (off by default in V1).

## Out of scope for V1 (later sets)
Cross-pillar (clip/cutting) fusion — their vectors aren't in the v4 space; per-user
memory/history; live web; reranker; audio. All deliberately deferred.

## Run
See [README.md](README.md): open the SSH tunnel, set `ASKRIG_DB_URL`, install deps,
`scripts/verify_embedding.py` (pre-flight), then `uvicorn app.main:app`.
