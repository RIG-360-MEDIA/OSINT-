# 06 — Content quality verification (Step 6)

**Verdict: CRITICAL FAIL — multiple BLOCKER content-correctness violations.**
This is the highest-stakes step per the user's
`feedback_cm_content_correctness.md` rule. Findings disqualify the
CM page from production.

## Sample 1 — Telangana spokesperson quotes (10 of 10 from same logistics article)

```
SELECT * FROM cm_spokesperson_quotes WHERE state='TG' LIMIT 10;
```
All 10 rows have:
- `speaker = "Vamshi Karangula"` (logistics industry person, NOT a
  Telangana politician)
- `source_url = "https://cargotalk.in/telangana-pushes-toward-next-gen-warehousing/"`
- `stance = "neutral_factual"`
- `party = NULL`
- Quotes are about Grade-A warehousing, e-commerce, q-commerce —
  zero political content.

**100% of state-scoped (TG) quotes in the DB are from a single
logistics article.** The "speakers extraction" pipeline is matching
on the article's `geo_primary='Telangana'` (because the article
mentions Telangana warehousing) but the *speaker* is a corporate
analyst, not a political figure.

**D-23 (BLOCKER)**: speaker extraction is missing political-relevance
filtering. Surface effect: `/api/cm/spokespersons?state=TG`,
`/api/cm/voice-share?state=TG`, `/api/cm/silence?state=TG` are all
populated by industry analysts, not politicians.

## Sample 2 — Top speakers across all states

```
SELECT speaker, count(*) FROM cm_spokesperson_quotes
GROUP BY 1 ORDER BY 2 DESC LIMIT 15;
```
| Speaker | Count | Type |
|---|---:|---|
| GECF | 10 | Org (Gas Exporting Countries Forum) |
| Kunal Maheshwari, CGO, Softlink Global | 10 | Software exec |
| Vamshi Karangula | 10 | Logistics industry |
| Surya Kant | 8 | Supreme Court justice |
| Dilip Thakore | 8 | Business journalist |
| TeamLease Services | 7 | Staffing firm |
| **"The article does not mention a specific named person"** | **7** | **LLM placeholder string written to DB** |
| Observers | 7 | Generic |
| Union Health Secretary | 6 | Federal bureaucrat |
| Sylvester Stallone | 6 | Hollywood actor |
| Unknown | 6 | Placeholder |
| Aayush Agarwal | 6 | Unknown person |
| Bikash Koley | 6 | Tech exec |
| Justice Mohammad Yousuf Wani | 5 | J&K judge |
| Ashwini Vaishnaw | 5 | Federal IT minister (only legit politician in top 15) |

**D-24 (BLOCKER)**: the literal string "The article does not mention
a specific named person" appears 7 times as a `speaker` value. Groq
returns this when it cannot extract a speaker; the speakers task is
inserting it as a row instead of treating it as a no-extraction
sentinel. See `backend/nlp/cm/speakers.py` validation logic.

**D-25 (BLOCKER)**: speaker pool is dominated by non-political
voices (cricketers, actors, judges, industry analysts, agencies).
Of top 15 speakers, only 1 (Ashwini Vaishnaw) is a politician.
"Spokesperson" surface for the CM page is completely unreliable.

## Sample 3 — Issues clusters (D-2 confirmed end-to-end)

```
SELECT id, state, label FROM cm_issues;
```
| ID | State | Label |
|----|-------|-------|
| 1 | NULL | India New Zealand Trade Agreement |
| 2 | NULL | Indonesia train accident scene |
| 3 | NULL | Iran Russia Diplomatic Talks |
| 4 | NULL | US State Visit Itinerary |
| 6 | NULL | Jakarta train accident scene (≈ duplicate of #2) |

- **Zero Telangana / AP issues.**
- All `state=NULL`, `intensity=0`, `trajectory='unknown'`.
- "Indonesia train accident scene" and "Jakarta train accident
  scene" are clearly the same news event clustered twice — clustering
  not deduplicating.

**D-26 (BLOCKER)**: `cluster_issues` task is producing world-news
clusters with no state attribution. CM page "Top Issues" panel
will show non-Indian news. Root cause appears to be that the
clustering input pool isn't filtered to TG/AP geo_primary articles.

## Sample 4 — Promises (12 rows, mixed quality)

| State | Party | Pledge sample | source_url quality |
|---|---|---|---|
| TG | INC | Mahalakshmi: Rs 2,500/mo women's allowance, free TSRTC bus, Rs 500 LPG | `thehindu.com/news/national/telangana/` (section landing, not specific article) |
| TG | INC | Rythu Bharosa: Rs 15K/acre/yr, Rs 12K/yr tenant, Rs 500 quintal bonus | same generic landing |
| AP | TDP | Yuva Galam: Rs 3K/mo unemployment for educated youth | `telugudesamparty.org/` (party homepage) |
| AP | TDP | Free public transport for women across APSRTC | same homepage |

**Pledge text quality**: ✓ — actual real INC/TDP manifesto items.
**Source URL quality**: ✗ — generic landing pages, not specific
manifesto pages. A user clicking "view source" cannot verify the
pledge.

**Status assignments**: 8 of 12 `broken`, 1 `kept`, 1 `stalled`,
1 `in_progress`, 2 `unknown`. **All 12 have `last_evidence_url=NULL`** —
no evidence backing the status verdict. Status was seeded by hand
without per-pledge proof.

**D-22 (HIGH)**: cm_promises rows need (a) per-pledge
`source_url` pointing to the specific article that captured the
pledge, and (b) `last_evidence_url` populated when status changes
from `unknown`.

## Sample 5 — Counter narratives + dissent

Both tables empty:
- `cm_counter_narratives`: 0 rows (Groq calls fail → all rejected)
- `cm_dissent_signals`: 0 rows (depends on per-speaker quote pairs;
  no political speakers seeded; 0 candidates)

When the Groq key is restored, counter narratives may start
generating, but the cite-grounding guardrail
(`backend/nlp/cm/counter_narrative.py:validate_cites`) only protects
*ID validity* — it does not check that the cited articles are
actually about the issue's politics. Combined with D-25 / D-26,
generated counter-narratives will cite logistics articles for
political issues.

## Sample 6 — Risk calendar (looks legitimate)
```
SELECT id, event_date, kind, risk_level, title FROM cm_risk_calendar
WHERE event_date >= CURRENT_DATE - 7 ORDER BY event_date LIMIT 15;
```
The risk calendar appears to be hand-curated with real events —
court hearings, parliamentary sessions, by-elections. This is
the only CM data surface that survives the audit.

## Sample 7 — Stance score distribution (32% unknown)
| Stance | Count | avg confidence |
|---|---:|---:|
| neutral_factual | 3295 | 0.92 |
| **unknown** | **1804** | 0.05 |
| opposition_attack | 915 | 0.83 |
| ruling_supportive | 204 | 0.84 |
| mixed | 1 | 0.70 |

**29% of articles labeled `unknown`** because Groq 401'd the call
(D-8). Confidence 0.05 means these rows should be filtered out at
read time but currently aren't.

## Live channel verification — 9/9 channel IDs are real
Cross-referenced channel IDs against YouTube. Each ID resolves to
the named Telugu news channel (V6 News, TV9 Telugu, etc.). 8 of 9
are currently live (Step 3 result). **No fabrication here** ✓.

## Defects added
| ID | Sev | Title |
|---|---|---|
| D-22 | HIGH | cm_promises rows have generic landing-page source_urls instead of specific article URLs; last_evidence_url 100% null |
| D-23 | **BLOCKER** | 100% of cm_spokesperson_quotes for state='TG' come from a single logistics article (non-political speaker) |
| D-24 | **BLOCKER** | "The article does not mention a specific named person" stored as a literal speaker name (7 rows) — speakers task fails to filter LLM no-extraction sentinel |
| D-25 | **BLOCKER** | Top speakers pool dominated by cricketers, actors, judges, agencies, industry analysts — political-relevance filter missing |
| D-26 | **BLOCKER** | cm_issues clusters are world-news ("Indonesia train accident", "Iran Russia Diplomatic Talks") with NULL state and zero intensity — clustering input not state-filtered |
