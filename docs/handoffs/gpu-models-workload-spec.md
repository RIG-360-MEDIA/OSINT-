# RIG — GPU model workloads (for GPU-sizing advice)

These are the models we run **on local GPUs** (via Ollama / TabbyAPI / sentence-transformers).
LLM-heavy overflow also spills to cloud (Groq/Cerebras), but the rows below are what
needs GPU. "Concurrency" = parallel in-flight requests we push at one box.

| # | Task | Model | Params | Quant / precision | Runtime | Prompt size | Output size | Concurrency (parallel) | Throughput we need | Latency profile | Est. VRAM | Current GPU |
|---|------|-------|--------|-------------------|---------|-------------|-------------|------------------------|--------------------|-----------------|-----------|-------------|
| 1 | **Directed sentiment** (stance + impact, JSON) | Qwen2.5-7B-Instruct | 7B | Q4_K_M (GGUF) | Ollama | ~1–1.5k chars (title+lead) | ~80 tokens | **12 per box** (×3 boxes) | ~560 scored/min sustained (backfill) | Batch, not interactive | ~6–10 GB | 3 boxes (t7/t3/t8) |
| 2 | **Topic classification** (15-bucket) | Qwen2.5-32B-Instruct | 32B | Q4_K_M | Ollama | ~1k chars | ~1 label (~10 tok) | 4–8 | few hundred/min | Batch | ~20–24 GB | 1 box (100.96.25.59, **currently down**) |
| 3 | **Same-event / gray-zone cluster judging** (v9) | Qwen (2.5-14B class) | 14B | Q4 | Ollama | pairwise text ~1–2k | short (yes/no+reason) | 10 | bursty per clustering run | Batch, latency-tolerant | ~10–12 GB | shared local + cloud overflow |
| 4 | **Multilingual embeddings** (clustering + retrieval) | LaBSE **v4** | ~470M | FP16 | sentence-transformers (GPU server :8055) | short text | 768-dim vector | large batch (256+) | embed every ingested article (~40k/day) | Throughput-bound | ~2–4 GB (grows with batch) | 4090 (embed server) |
| 5 | **General LLM node / broadcast writing** | Qwen3-14B | 14B | 4-bit EXL2 | TabbyAPI (:5000) | 1–4k | up to ~1–2k tokens | low (content gen) | on-demand | Semi-interactive | ~10–12 GB | 4070 (TRIJYA-8) |
| 6 | **Broadcast TTS** (voice synthesis) | Chatterbox TTS / CosyVoice2 | — | FP16 | Python (GPU) | script text | audio | 1–2 | near-real-time for hourly broadcast | Latency-sensitive | ~4–8 GB | 4070/4090 (TTS lab) |

## Section B — CLOUD inference (Groq / Cerebras)

These tasks run through a **unified LLM pool** that prefers local GPU (Ollama) when available,
then spills to **Groq** (20 API keys), then **Cerebras**. So most rows below *can* run on GPU
too — they're on cloud today for burst capacity / because a local box was down. Cloud has no
VRAM cost but is **rate-limited by tokens-per-day (TPD)** and adds network latency + $.

| # | Task | Model(s) | Provider | Runtime today | Volume / burst | Limit | Why cloud (vs GPU) |
|---|------|----------|----------|---------------|----------------|-------|--------------------|
| 7  | **Report / daily-brief narrative** | Qwen3-32B | Groq | cloud | bursty (per report) | 500k **TPD per key** ×20 keys | heavy, latency-tolerant; no dedicated 32B GPU free |
| 8  | **Topic classification (fallback)** | Qwen3-32B | Groq | cloud (local 32B box down) | ~1.3k/hr | TPD | would move back to local GPU if the 32B box returns |
| 9  | **Keyword sentiment (on-demand, client API)** | Qwen/Llama class (classification) | Groq | cloud | real-time client calls | RPM/TPD | client-facing → needs always-on, no single-box dependency |
| 10 | **Substrate summaries + claims** (v3 extraction) | pool (Qwen3-32B → fallbacks) | Groq → Cerebras | cloud | high, continuous | TPD | high volume; overflow beyond local capacity |
| 11 | **Gray-zone cluster judging (overflow)** | Qwen class | Groq / Cerebras | local + cloud | bursty per clustering run | TPD | spills to cloud when local Ollama saturated |
| 12 | **Source-grounded content generation** | Qwen3-32B (writer) + Llama-3.3-70B (verifier) | Cerebras / Groq | cloud | on-demand | TPD | 70B verifier too big for our local cards |
| 13 | **Ask-RIG RAG answers** (client chat) | pool (Qwen3-32B → fallbacks) | Groq → Cerebras | cloud | client-facing, interactive | RPM/TPD | needs low latency + high availability |
| 14 | **Sentiment/cuttings backfill (cloud lane)** | Qwen class | Groq + Cerebras | cloud (overflow) | batch | TPD | used when local t7/t3/t8 are busy |

**Cerebras fallback tail (separate token budgets):** `qwen-3-235b-a22b` (now deprecated), `zai-glm`, `gpt-oss`, `llama-3.3-70b`. The pool rotates through these when the primary model's TPD is exhausted.

## How to read this for a GPU recommendation
- **VRAM** is driven by *model size (at the quant) + KV-cache for the concurrency*. Rows 1 & 3 (7B/14B @ Q4, high parallel) fit **12–16 GB** cards. Row 2 (32B @ Q4) needs **24 GB** minimum (tight with parallelism) — or step down to a 14B (topic is a simple task, a 7–14B is plenty). Rows 4–6 are small-model / throughput or latency jobs.
- **Two distinct GPU profiles here:**
  - **Throughput/batch** (rows 1, 2, 4) — wants high **memory bandwidth** + enough VRAM for many parallel sequences. Best value: **RTX 4090 (24 GB)** or **A6000/L40S (48 GB)** if you want 32B + big batches on one card.
  - **Latency/interactive** (rows 5, 6) — smaller models, wants fast single-stream; a **12–16 GB** card (4070 Ti / 4080) is fine.
- **If consolidating to one card:** a single **RTX 4090 (24 GB)** covers rows 1, 3, 4, 5, 6 comfortably and can run the 32B (row 2) at Q4 with modest concurrency. For heavy 32B + big batches simultaneously, go **48 GB (A6000/L40S)** or two 24 GB cards.
- **Context length** across all tasks is short (≤4k), so KV-cache is modest — VRAM is dominated by weights, not context.

## Notes for whoever advises you
- Everything is **quantized (Q4 / 4-bit EXL2)** — full-precision numbers would be ~2–4× these VRAM figures; we don't need FP16 weights.
- We deliberately proved **7B ≈ 32B for sentiment** (32B gave no lift) — so we favor smaller models where quality holds. Topic could likely drop to 7–14B too.
- Cloud (Groq/Cerebras) already absorbs overflow, so the local GPU only needs to cover **steady-state throughput**, not peak.
