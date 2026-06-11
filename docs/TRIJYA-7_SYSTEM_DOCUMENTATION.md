# TRIJYA-7 (RTX 4090) — Compute Resource Documentation

> **Prepared**: 2026-05-27
> **System owner**: RIG Surveillance — local inference node
> **Audience**: TRIJYA admin / management review

---

## 1. Purpose — Why this system is being used

TRIJYA-7 is the **local LLM inference node** for RIG Surveillance, a multi-pillar news-intelligence platform processing ~3,000–4,000 news articles per day across 414 RSS sources in 6+ languages (English + Hindi, Telugu, Tamil, Bengali, Marathi, Malayalam, Kannada, Odia).

**The 4090 is being used because**:
- Each article requires **LLM-based structured extraction** (subject/predicate/object claims, named entities, quotes, locations, events, stance scoring, narrative classification, multi-language translation).
- Commercial LLM APIs (Groq, Cerebras) cap us at ~12,000 articles/day on free tier — **insufficient for our 4,000-articles/day target with backfills**.
- A single RTX 4090 running quantized open-weights models gives us **roughly equivalent throughput at zero per-token cost**, eliminating the daily-quota bottleneck.
- This is **the only path to scaling beyond 50–100 sources** without recurring API expenditure.

**What we'd do without it**: cap processing at ~12K articles/day, abandon overnight backfills, scale back from 414 to ~50 sources, drop non-English language coverage.

---

## 2. How it connects to the project

| Property | Value |
|---|---|
| Hostname | TRIJYA-7 |
| Internal IP (Tailscale VPN) | `100.92.126.27` |
| Port | `11434` (Ollama HTTP API) |
| Authentication | None (private Tailscale mesh — not exposed to public internet) |
| Network path | RIG-backend (Hetzner Cloud, Germany) → Tailscale tunnel → TRIJYA-7 (India) |
| Inference engine | **Ollama** (open-source local LLM server) |
| Active model | `qwen3:30b-a3b` (Alibaba Qwen 3, 30B-parameter Mixture-of-Experts, ~3B active per token) |

**Integration point** in code: `backend/nlp/groq_client.py` — the `_OLLAMA_BASE` constant routes a subset of LLM calls from the production backend to TRIJYA-7 through the Tailscale overlay network.

---

## 3. Workflows, tasks, and processes running on TRIJYA-7

TRIJYA-7 is part of a **unified 3-provider LLM pool** (Groq + Cerebras + Ollama). The dispatcher routes work to whichever provider has free capacity, with Ollama serving as the **always-available local fallback** when commercial quotas are exhausted.

### Tasks served by TRIJYA-7

| Task | Frequency | Description |
|---|---|---|
| **Substrate extraction** (v3) | per-article, real-time | Reads a news article → returns structured JSON: article type, summaries, locations, events, quotes, claims (subject/predicate/object), entity stances, numbers, register classification. |
| **D1 SPO re-extraction** | nightly cron 00:05 UTC | One-shot reprocess of 80,000 historical articles to populate subject/predicate/object triples. |
| **Quote translation** | per-quote, real-time | Non-English news quotes → English translations. |
| **Article body translation** | per-article, real-time | Indic-language article bodies → English. |
| **Stance scoring** | per-article | Per-actor sentiment / supportive-vs-critical classification. |
| **Entity-link backfill** | periodic | Resolves subject_text to canonical entity IDs. |

### Operational details
- **Concurrency cap**: 4 simultaneous requests (`_LOCAL_MAX_CONCURRENT = 4`) to prevent KV-cache thrashing.
- **Network latency**: ~20-50ms per request over Tailscale (India ↔ Germany).
- **Daily volume**: typically **5,000–20,000 inference calls/day**, varying with commercial-API quota availability.
- **All inference is text-only** — no images, no audio, no PII processing.

---

## 4. Dependencies, integrations, resources

### Software stack on TRIJYA-7
| Component | Purpose |
|---|---|
| **Ollama server** (`/usr/local/bin/ollama serve`) | LLM hosting daemon |
| **Tailscale client** | Private VPN connectivity to Hetzner |
| Model weight cache (`~/.ollama/models`) | qwen3:30b-a3b weights (~18 GB on disk) |

### External integrations
- **None outbound from TRIJYA-7.** The 4090 only receives requests from the Hetzner backend over the private Tailscale tunnel.
- **No public network exposure.** Port 11434 listens only on the Tailscale interface.
- **No user data, credentials, or PII stored on TRIJYA-7** — requests arrive, inference returns, no persistent state.

### Resources consumed
| Resource | Typical usage |
|---|---|
| GPU VRAM | ~22 GB of 24 GB during inference |
| GPU utilization | 30-70% when actively serving |
| Disk | ~25 GB (model + Ollama runtime + logs) |
| Network | ~5-15 GB/day inbound (prompts) + ~2-5 GB/day outbound (completions) |
| Power | Workstation-typical for a 4090 under partial load |

### Monitoring & control
- **Keepalive cron** on Hetzner (`ollama_keepalive.sh` runs every 4 hours) pings TRIJYA-7 to keep the model resident in GPU memory.
- **Failure mode**: if TRIJYA-7 is unreachable, requests automatically fall back to Groq/Cerebras commercial APIs — **no data loss, no pipeline interruption**.

---

## 5. Summary for management

- TRIJYA-7 functions as a **dedicated background compute resource** for the RIG Surveillance news-intelligence pipeline.
- The 4090 GPU runs a single, locally-hosted open-source language model used only for structured-data extraction from news articles.
- **Zero external connectivity** beyond the encrypted Tailscale VPN to one server (Hetzner).
- **Zero data egress** to commercial providers — all inference happens on-machine.
- **Zero financial cost** of operation beyond electricity.
- Removal of this resource would force the project to either dramatically reduce scope or incur substantial recurring API costs (~ $300–500/month at commercial rates for equivalent throughput).

---
