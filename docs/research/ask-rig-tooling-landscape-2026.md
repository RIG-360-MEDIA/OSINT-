# Ask-RIG — best-in-class tooling + what to add next (researched June 2026)

Net research across agent frameworks, deep-research agents, memory, rerankers,
news-bias/framing, eval/observability, Indic TTS, and web extraction — mapped to
what Ask-RIG should adopt and what users will actually want.

## Verdicts by category (what's best, and our pick)

| Area | Best open-source (2026) | Pick for Ask-RIG | Why |
|---|---|---|---|
| **Agent framework** | LangGraph (mature orchestration) · Pydantic AI (type-safe, FastAPI-style) · LlamaIndex (RAG-first) | **Pydantic AI** (+ LangGraph if graphs get complex) | Pydantic AI mirrors our FastAPI+Pydantic stack exactly — least friction to wrap our tools |
| **Deep-research loop** | gpt-researcher (92% cite-accuracy, swappable/local) · **STORM** (Stanford, multi-perspective) · LangChain Open Deep Research (MCP) | **Port STORM's multi-perspective** pattern | STORM interviews "experts from different angles" = literally our cross-language framing moat |
| **Agent memory** | Mem0 (drop-in, token-efficient) · **Zep/Graphiti** (temporal knowledge graph, 27k★) · Letta (memory-as-OS) | **Mem0 now → Graphiti later** | Mem0 = 5-line threads/prefs. Graphiti's *temporal* graph tracks how an entity's stance shifts over time = a real moat |
| **Reranker** | MXBai-v2 (Qwen, open SOTA) · ColBERT (late-interaction) · Contextual AI multilingual · AnswerDotAI **rerankers** (unified swap API) | **rerankers wrapper** + a multilingual SOTA on GPU | One-line A/B across models; multilingual matters for TE/HI |
| **Eval / observability** | Ragas (RAG metrics) · DeepEval (broad + CI/CD + multi-turn) · **Langfuse** (obs leader) · Phoenix | **Langfuse** + DeepEval CI | Trace cost/latency/faithfulness per query before scaling; quality-regression gates |
| **News bias/framing** | person-oriented framing analysis · LLM Media Bias Detector · GDELT themes | **Build F4 on `article_stances`** | Validates our moat: per-language stance contrast on one event |
| **Indic TTS (audio)** | **IndicF5** (AI4Bharat, 11 langs incl TE/HI, near-human) · Indic Parler-TTS | **IndicF5** | "Listen to your brief in Telugu/Hindi" — unique to an Indic product |
| **Web extraction** | **Crawl4AI** (local, LLM-ready markdown, −67% tokens) · Firecrawl (managed) | **Crawl4AI** (augment trafilatura) | JS-rendered pages + clean markdown for the Research tab |

## Ranked additions (highest leverage first)

**Tier 1 — build next**
1. **The agent (Set 4)** — Pydantic AI loop wrapping our existing tools (corpus_search, web_search, entity_feed, find_similar) + **Mem0** threads. Port **STORM/gpt-researcher** patterns for multi-step, multi-perspective research.
2. **Langfuse observability** — every query traced (cost, latency, faithfulness). Cheap, essential before real users.
3. **Cross-language framing contrast (Set-1 F4, the moat)** — EN vs TE vs HI stance on one event. Research confirms this is a genuine differentiator; we already have `article_stances`.

**Tier 2 — users will love these**
4. **Audio brief (IndicF5)** — morning brief read aloud in TE/HI/EN. A paid feature no English-first competitor has.
5. **Model Council** (Perplexity's 2026 hit) — answer through 2–3 models, surface agreement/disagreement = a trust signal. Nearly free with our multi-key pool.
6. **Crawl4AI** web upgrade — richer, JS-capable extraction → better Research answers.
7. **Reranker upgrade** — `rerankers` wrapper + mxbai-v2/Contextual multilingual on a GPU (banks the +22 MRR we measured).

**Tier 3 — deeper moat**
8. **Graphiti temporal graph** — "how has X's stance on Y shifted over months?"
9. **Blindspot / source-diversity view** (Ground-News style) — which stories are over/under-covered, by which side.
10. **DeepEval CI gates** — block quality regressions on every change.

## Sources
Agent frameworks · deep research · memory · rerankers · bias · eval · TTS · crawl — see the URL list captured in the session research (firecrawl.dev, alicelabs.ai, github assafelovic/gpt-researcher, langchain-ai/open_deep_research, Stanford STORM, getzep/Graphiti, AnswerDotAI/rerankers, AI4Bharat/IndicF5, Langfuse, Crawl4AI).
