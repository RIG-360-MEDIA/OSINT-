# Chronicle V2 — Full Analysis: Pipeline, Findings, and Clustering Noise
**Date:** 2026-06-07  
**Story tested:** Grievance Platform (`e8a5d010-d67e-407b-a528-ab89e5a39bc2`)  
**Scope:** What V2 did, what it found, which clustering steps added noise, why, and how to fix them.

---

## Part 1 — What V2 Does (the pipeline)

### Why V1 was insufficient

V1 feeds all 88 article **titles** into one LLM call and asks it to reconstruct a timeline. The LLM is not reading the articles — it is pattern-matching on headlines. It cannot detect:

- What changed *between* time periods
- What was announced and then silently dropped
- Who entered or left the story at a precise moment
- Coverage silences (absent = data)
- Patterns that are only visible across the full arc

### The V2 two-phase pipeline

**Phase 1 — Per-window temporal extraction (sequential)**

- Articles sorted chronologically, bucketed into 3-day windows
- Each window gets a separate LLM call
- Input: article titles + `lead_text_translated` / `summary_preview` (actual content, not just titles)
- Each call receives the previous window's summary as context
- Output per window:
  ```json
  {
    "window_summary": "factual 2-3 sentence description",
    "concrete_events": ["specific actions, not topics"],
    "active_actors": ["ActorName: what they did"],
    "tone": "neutral/supportive/critical/alarmed/manufactured + why",
    "notable_quotes": ["speaker: quote"],
    "silence": "what you'd expect covered here but wasn't"
  }
  ```

**Phase 2 — Cross-window synthesis**

- Receives all window extractions as structured input
- Explicitly told to reason *across* windows, not within them
- Looks for: shifts between windows, silences, who appears/disappears at precise moments, patterns only visible across the full arc
- Produces the same JSON contract as V1 (`event_chain`, `insights`, `actors`)

**Key architectural difference:** V1 sees one flat document. V2 sees a temporal sequence of structured intelligence — the gaps and changes between windows are explicit data, not implicit.

---

## Part 2 — What V2 Found on the Grievance Platform Story

### Window structure (88 articles, 8 windows)

```
Window 1: 2026-04-24             →  1 article
Window 2: 2026-04-30 → 05-02    → 13 articles
Window 3: 2026-05-03 → 05-05    →  4 articles
Window 4: 2026-05-07 → 05-09    → 48 articles  ← THE SPIKE
Window 5: 2026-05-10 → 05-12    → 16 articles
Window 6: 2026-05-13             →  2 articles
Window 7: 2026-05-25             →  2 articles
Window 8: 2026-05-29 → 05-31    →  2 articles
```

Window 4 (48 articles in 3 days) is the Collectors' Conference. This concentration has major downstream consequences for clustering (see Part 3).

---

### V1 vs V2 — Event Chain

**V1 (5 events — saw only Window 4 peak, missed everything else):**

| Date | Signal | Event |
|---|---|---|
| 2026-04-30 | reactive | Ponguleti Srinivas Reddy announces 3-month Praja Darbar deadline |
| 2026-05-07 | escalation | Collectors' Conference — Singapore Model + ₹10L crore debt narrative |
| 2026-05-08 | resolution | Naidu mandates 24-hour clearance for e-files and vehicle registrations |
| 2026-05-09 | organic | Transport Minister executes 24-hour order |
| 2026-05-12 | resolution | Automatic approvals if 24-hour deadline missed |

**V2 (7 events — reads the full arc):**

| Date | Signal | Event |
|---|---|---|
| 2026-04-24 | organic | Naidu announces 40 lakh solar panel installations for agricultural power |
| 2026-04-30 | reactive | University course restructuring + GoM calls for transparent job-creation data |
| 2026-05-03 | escalation | AI advisory council constituted; vehicle dealers authorised as registration points |
| 2026-05-07 | manufactured | SIPB approves ₹11L crore investments at Collectors' Conference |
| 2026-05-10 | bureaucratic executor | Transport Dept mandates 24-hour timeline; Transco board reshuffled |
| 2026-05-25 | media amplifier | Union Minister Pemmasani surfaces — BSNL and India Post results announced |
| 2026-05-29 | organic | Naidu directs Yogandhra-2026 with 1 crore participant target |

**What V1 missed entirely:** events on Apr 24, Apr 30, May 3, May 25, May 29.  
**Why:** V1 built its timeline from headline frequency. 48 articles in 3 days dominated the centroid; everything outside that spike was underweighted to the point of invisibility.

---

### V1 vs V2 — Insights

**V1 insights (from headline pattern-matching):**

1. `[high]` What explains the sudden shift from general Praja Darbar petitions to a specific 24-hour digital metric?
2. `[medium]` Why is Transport the primary pilot for 24-hour governance?
3. `[high]` What is the strategic function of the ₹10L crore debt narrative?
4. `[medium]` Why was Transgender welfare buried in the efficiency news cycle?

**V2 insights (from cross-window temporal reasoning):**

1. `[high]` **What explains the total disappearance of the 40 lakh solar panel initiative after Day 1?** — *Impossible from V1. Requires comparing Window 1 against all subsequent windows explicitly.*
2. `[medium]` **Why did media focus shift from State CM reforms to Union Minister achievements between Windows 6 and 7?** — *Impossible from V1. Requires tracking actor presence across the arc.*
3. `[high]` What explains aggressive 24-hour clearance + AI governance push simultaneously with the debt crisis narrative?
4. `[medium]` Why were 5,000 temples construction and full-scale employee promotions announced without funding details?

**The silence-based insight (solar panels) is the most important.** It is only detectable because Phase 1 Window 1 explicitly recorded "40 lakh solar panel target" and Phase 2 noticed that zero subsequent windows mentioned it. V1 reads all 88 titles simultaneously — the single Apr 24 article was drowned out by 47 May 7–9 articles.

---

### V1 vs V2 — Actors

| V1 | V2 |
|---|---|
| N. Chandrababu Naidu | N. Chandrababu Naidu |
| District Collectors / Bureaucracy | **Nara Lokesh** ← missed by V1 |
| Mandipalli Ramprasad Reddy | Mandipalli Ramprasad Reddy |
| Pemmasani Chandra Sekhar | Pemmasani Chandra Sekhar |
| — | **Group of Ministers (GoM)** ← missed by V1 |

Nara Lokesh appears in Windows 2–3 (education/IT reform thread), then disappears — V2 caught this because it tracks actors per window. V1 missed him because he appears in low-frequency windows outside the Collectors' Conference spike.

---

### The meta-finding: what this story is actually about

**V1's interpretation:** A story about petition backlogs → Praja Darbar mechanism → 24-hour digital governance pilot.

**V2's interpretation:** Naidu simultaneously launched 6–7 distinct governance initiatives (solar, AI, university reform, vehicle digitisation, temple construction, Yogandhra, SIPB investment promotion) across different domains over 37 days, anchoring all of them under a single political framing: *"₹10 lakh crore debt demands radical administrative efficiency."* The Praja Darbar is one instrument. The 24-hour clearance is one instrument. The solar initiative was announced, served its launch purpose, and was dropped with no follow-up.

No journalist covering any single beat would see the pattern. V2 sees it because it compares window-to-window deltas. This is a manufactured multi-domain political narrative campaign — not a governance story.

---

## Part 3 — Clustering Noise Analysis

### Attach-score distribution

```
1.00  →  47 articles   (core: same event, same actors, same dates)
0.99  →  13 articles   (core periphery: same event, slightly different frames)
0.98  →   6 articles
0.97  →   1 article
0.96  →   2 articles
0.95  →   3 articles
0.93  →   1 article    ← Layer 2 begins here (hub-attached)
0.90  →   2 articles
0.89  →   3 articles
0.88  →   1 article
0.87  →   1 article
0.85  →   3 articles   ← Layer 3 begins here (LABSE bleed)
0.75  →   1 article
0.69  →   3 articles
0.67  →   1 article
```

Three layers, three different causal mechanisms.

---

### Layer 1: True core (score 0.95–1.00, ~72 articles)

These articles are genuinely about the same story cluster: Praja Darbar → Collectors' Conference → 24-hour clearance mandate. Same actors (Naidu, Mandipalli, district collectors), same dates (Apr 30 – May 13), same policy thread. The clustering algorithm is **correct** here.

**However:** two anomalies score 1.00 that are not core:

- `1.00 | 2026-05-01 | Naidu inaugurates LV Prasad Eye Care Centre in Krishna district`  
  → A hospital inauguration. Scores 1.00 because LABSE sees "Naidu + inaugurates + district + administration" — same pattern as governance reform articles.

- `1.00 | 2026-05-07 | India Post working to double its revenue growth, says Union Minister Pemmasani`  
  → A central government story. Scores 1.00 because Pemmasani was physically at the Collectors' Conference on May 7 and gave this statement there. Same event, different topic.

**Root cause:** The attach score is cosine similarity to the cluster centroid, not relevance to the cluster's actual topic. If an article shares entity patterns with the centroid (Naidu + administrative verb + district), it scores high regardless of subject matter.

---

### Layer 2: Hub-attached articles (score 0.88–0.95, ~8 articles)

These articles are loosely related AP governance content that got pulled in via the Collectors' Conference hub.

**Mechanism — the hub gravity effect:**

The Collectors' Conference (May 7–9) produced 48 articles in 3 days. These 48 articles discussed: solar energy, AI governance, university reform, vehicle registration, debt management, grievance redressal, SIPB investments, Yogandhra, temple construction — all in the same event. In the similarity graph used by Louvain:

```
Solar article (Apr 24)
    ↕ high similarity
Collectors' Conference article: "CM discusses agri modernisation including solar targets" (May 7)
    ↕ high similarity
24-hour clearance article (May 8)
```

Louvain sees: A is similar to B, B is similar to C → A, B, C are one community. This is **graph transitivity** — A and C are in the same cluster not because they are similar to each other, but because they share a common hub neighbour B.

**Specific hub-attached articles:**

| Score | Article | Why attached |
|---|---|---|
| 0.93 | Solar panels agri power (Apr 24) | Collector's Conference mentioned solar in the same breath |
| 0.95 | Employee promotions (May 4) | Naidu + government + employee action pattern |
| 0.89 | Revenue Association work burden (May 2) | Government + employees + AP pattern |
| 0.89 | J.P. Nadda medical infrastructure (May 7) | Central minister + AP + conference timing |

**The hub effect is not fully noise.** These articles ARE part of the same political narrative — Naidu governance reform. But they are separate stories that happen to share political actors and timing. The clustering algorithm cannot distinguish "same event" from "same political actor, same month."

---

### Layer 3: LABSE bleed (score 0.55–0.87, ~8 articles)

These are genuine false positives — articles with no real connection to the story.

#### False positive 1: Ghana article (score 0.85)
```
0.85 | 2026-05-11 | Minister cuts sod for 24-Hour Economy Market in Kassena-Nankana West
```
**Why it scored 0.85:**  
LABSE (Language-Agnostic BERT Sentence Embedding) is trained for semantic similarity across languages. It does not understand geography. The phrase pattern `"Minister + 24-Hour + Economy + Market"` is semantically very close to `"Minister + 24-hour + clearance + governance"`. LABSE maps both to nearly the same region of embedding space because it shares nouns (Minister, hour, economy), a number (24), and an administrative context. No geographic grounding exists in the model.

#### False positive 2: Telugu stomach bloating article (score 0.69)
```
0.69 | 2026-05-07 | Andhra: ఆరు నెలలుగా తగ్గని కడుపు ఉబ్బరం.. (stomach bloating for 6 months)
```
**Why it scored 0.69:**  
Telugu government-health vocabulary shares token-level patterns with governance articles. Words like "ఆందోళన" (concern/anxiety), "అధికారులు" (officials), "ప్రజలు" (public/people) appear in both health complaints and governance news in Telugu. The LABSE embedding for a Telugu article about a public health complaint in Andhra will have moderate cosine similarity to Telugu governance articles about public services — same geographic marker (Andhra), same population-focused vocabulary.

#### False positive 3: Kannada organic farming (score 0.67)
```
0.67 | 2026-05-01 | ನರಗುಂದ | 60 ಎಕರೆ ಜಮೀನಿನಲ್ಲಿ ತರಹೇವಾರಿ ಬೆಳೆಗಳು: ಲಾಭ ತಂದ ಸಾವಯವ ಕೃಷಿ
```
**Why it scored 0.67:**  
The story cluster's centroid includes agricultural policy articles (solar panels for agri power, GoM + employment). Kannada agricultural content shares embedding proximity with Telugu/English agricultural governance content because LABSE uses cross-lingual alignment — it maps similar concepts across languages to similar embedding regions. "Farming + land + profit + government scheme" in Kannada lands near "agricultural power + government initiative + AP" in Telugu/English.

#### False positive 4: Maharashtra Police Housing (score 0.69)
```
0.69 | 2026-05-12 | Maharashtra Police Housing Scheme News: जनता की सुरक्षा करने वाले पुलिसकर्मियों को मिलेगा अपना घर
```
**Why it scored 0.69:**  
Hindi article about a government housing scheme for police. The cluster centroid includes employee welfare articles (employee promotions, government housing). "Government + employees + housing + scheme" in Hindi maps near "government + employees + welfare + AP" in English/Telugu. Different state, same vocabulary pattern.

#### False positive 5: BSNL Hindi article (score 0.75)
```
0.75 | 2026-05-25 | बीएसएनएल का राजस्व ₹21,000 करोड़ से बढ़कर ₹25,000 करोड़
```
**Why it scored 0.75:**  
Higher score than Maharashtra because Union Minister Pemmasani was physically present at the AP Collectors' Conference and made statements about BSNL and India Post there. Other articles from the same conference event (May 7) scored 1.00. The BSNL Hindi article published May 25 covers the same topic (Pemmasani/BSNL revenue) but two weeks later and in Hindi — slightly lower similarity to the centroid but still pulled in because Pemmasani + BSNL + revenue + crore is a near-identical semantic pattern.

---

## Part 4 — Root Causes Summary (the specific algorithm steps that added noise)

### Step A — LABSE multilingual geography blindness

**Where in the algorithm:** The embedding generation step. Every article is independently embedded with no geographic constraint.

**What goes wrong:** LABSE is trained to map semantically similar concepts across languages to the same region of embedding space. This is the feature that makes it good for multilingual content. But it treats "Minister + 24-hour + public" as semantically equivalent regardless of whether the minister is in Ghana or Andhra Pradesh. No geographic anchor exists at the embedding level.

**Noise introduced:** Ghana article (0.85), potentially any article worldwide that uses governance + efficiency + administration vocabulary.

**Fix direction:** Post-embedding geographic filter. Before building the similarity graph, compute each article's primary geographic entity. Articles whose `source_country` or `geo_primary` is more than 1 degree of separation from the cluster's `subject_country` should have their edge weights penalised or removed before Louvain runs.

---

### Step B — Hub gravity (Collectors' Conference 48-article spike)

**Where in the algorithm:** The Louvain community detection step. Louvain maximises modularity — it wants dense internal edges. A 48-article hub creates a very dense internal subgraph. Any article with even moderate similarity to *any* of those 48 hub articles gets pulled into the community because the hub raises the overall community edge density.

**What goes wrong:** The hub represents one *event* (the conference) that discussed many *topics* simultaneously. Every topic mentioned at the conference has at least one hub article pointing toward it. This creates transitive bridges: `Solar article → Conference+solar article → Grievance article` → all in one community.

**Noise introduced:** All Layer 2 articles (0.88–0.95). Also causes V1 to miss everything outside the spike — the hub's 48 articles dominate the centroid so heavily that the centroid moves toward "May 7–9 conference content" and away from the broader story.

**Fix direction:** Hub detection + weight normalisation. Before Louvain, detect articles with abnormally high degree in the similarity graph (degree >> median + 2σ). For these hub articles, cap their edge contribution to a maximum of `k` neighbours (e.g., top-10 by similarity). This prevents a 48-article event from becoming a gravity well that absorbs the entire cluster neighbourhood.

---

### Step C — Louvain transitivity (A~B, B~C → same community)

**Where in the algorithm:** The core community detection step.

**What goes wrong:** Louvain finds communities where internal edges are denser than expected by chance. If A is similar to hub B and C is similar to hub B, Louvain may put A, B, C in the same community even if A and C have near-zero direct similarity. The hub mediates their membership.

**Noise introduced:** This is the mechanism behind all Layer 2 and some Layer 3 articles. Without the hub articles, A and C would never be in the same community.

**Fix direction:** Post-Louvain attach-score filtering (already partially done via `attach_score >= 0.60`). But the threshold is set globally. A better approach: compute the attach score relative to the *cluster centroid after removing hub articles* from the centroid calculation. Hub articles inflate the centroid toward their dense neighbourhood; removing them from the centroid computation gives a cleaner measure of whether a peripheral article actually belongs.

---

### Step D — Attach score threshold calibration

**Where in the algorithm:** The post-clustering filter applied when building `story_cluster_members`.

**Current state:** V1 uses `attach_score >= 0.60`. V2 used `attach_score >= 0.55` — this was a mistake that introduced significant noise into Phase 1 window extraction.

**Score boundaries by content type:**

| Score range | What you get |
|---|---|
| ≥ 0.95 | Pure core — same event, same policy thread |
| 0.88–0.95 | Related AP governance, hub-transitive |
| 0.85–0.88 | Language-similar noise begins (Ghana article at 0.85) |
| 0.60–0.85 | Mixed: some legitimate periphery, some multilingual false positives |
| < 0.60 | Mostly noise: Maharashtra, stomach bloating, Kannada farming |

**Recommended thresholds:**
- For Chronicle V2 Phase 1 (LLM reads article text): use `>= 0.90` — high precision, low noise
- For article list display and metadata counts: use `>= 0.60` — current behaviour, acceptable
- For clustering membership during training: keep `>= 0.60` but add geographic filter

---

### Step E — Score 1.00 anomaly (cosine similarity vs topic relevance)

**The problem:** `attach_score = cosine_similarity(article_embedding, centroid_embedding)`. A 1.00 score means the article's embedding is nearly identical to the cluster centroid. But the centroid is computed as the average of all member embeddings — including hub articles that discuss many topics.

**Result:** `Naidu inaugurates LV Prasad Eye Care Centre` scores 1.00 because:
- The centroid embedding reflects "Naidu + administrative action + district + AP"
- Eye care inauguration uses the same pattern: "Naidu + inaugurates + Krishna district"
- LABSE does not distinguish the topic (health vs governance)

This means the attach score measures *actor and context pattern similarity*, not *topic relevance*. A story about Naidu doing anything in AP will score high in a cluster about Naidu governance reforms.

**Fix direction:** Hybrid scoring. Combine cosine similarity (captures actor/context) with a topic similarity score (e.g., keyword overlap with the cluster's `representative_title` and `topic` field). Something like:  
`final_score = 0.7 * cosine_similarity + 0.3 * keyword_relevance_score`  
This would penalise "LV Prasad Eye Care" (no keywords overlap with "grievance redressal") while keeping core articles.

---

## Part 5 — Recommended Fixes (prioritised)

### Fix 1: Geographic entity post-filter (HIGH PRIORITY — eliminates Ghana-type noise)
After clustering, for each cluster with a `subject_country`, remove any member article where:
- `a.source_country != cluster.subject_country` AND
- `a.geo_primary` is not in the cluster's `subject_country` or `subject_region` AND
- `a.attach_score < 0.95`

This preserves legitimately cross-geographic articles (Union Minister Pemmasani — central government, covered AP) while removing Ghana, Maharashtra, and Kannada false positives.

### Fix 2: Hub detection + edge-weight capping (MEDIUM PRIORITY — fixes transitivity noise)
Before Louvain runs:
1. Compute degree of each node in the similarity graph
2. Flag nodes where degree > median + 2σ as hub articles
3. For each hub article, keep only the top-K (e.g., 15) strongest edges
4. This prevents a 48-article conference from creating 2,000+ transitive edges

### Fix 3: V2 Phase 1 threshold fix (IMMEDIATE — fixes the V2 noise we introduced today)
In `_fetch_story_data_v2`, change `attach_score >= 0.55` to `attach_score >= 0.90`.
This makes V2 Phase 1 read only the high-confidence core articles — clean signal for the LLM.

### Fix 4: Centroid recalculation excluding hub articles (LOW PRIORITY — longer term)
After clustering, recompute the cluster centroid using only articles with degree ≤ median in the original similarity graph. Use this "hub-free centroid" for the final attach_score calculation. This would give more accurate scores to peripheral articles and fix the score 1.00 anomaly for unrelated articles.

### Fix 5: Hybrid topic-weighted attach score (LOW PRIORITY — requires reprocessing)
Replace pure cosine attach_score with:
`final_score = 0.7 * cosine_similarity + 0.3 * topic_keyword_overlap`
Where topic_keyword_overlap is computed between the article and the cluster's `representative_title` + `topic` field. Prevents actor-pattern similarity from dominating over topic relevance.

---

## Summary Table

| Noise type | Example | Score | Cause | Fix |
|---|---|---|---|---|
| Geographic bleed | Ghana 24-Hour Market | 0.85 | LABSE has no geography | Post-filter by source_country |
| Multilingual pattern | Kannada organic farming | 0.67 | Cross-lingual embedding proximity | Geographic filter |
| Language bleed | Telugu stomach bloating | 0.69 | Telugu gov vocab overlaps | Geographic + topic filter |
| Hub transitivity | J.P. Nadda medical infra | 0.89 | Louvain via conference hub | Hub edge-weight capping |
| Actor pattern (score 1.00) | LV Prasad Eye Care | 1.00 | Centroid = actor pattern not topic | Hybrid scoring |
| Conference topic scatter | BSNL, India Post | 0.75–1.00 | Conference discussed everything | Hub detection |
| V2-specific noise | Solar, Yogandhra | 0.55–0.88 | V2 threshold too low | Use 0.90 for Phase 1 |

---

## Immediate action for V2 production

Before making V2 the default, apply Fix 3 only (one line change):

```python
# In _fetch_story_data_v2(), change:
AND m.attach_score >= 0.55
# To:
AND m.attach_score >= 0.90
```

This alone eliminates the Ghana article, stomach bloating, Maharashtra police, Kannada farming, and most hub-transitivity noise from Phase 1 extractions — making V2 read only what genuinely belongs to the story. The article list displayed to users (via `/api/chronicle/{id}/articles`) stays at 0.60 for breadth.
