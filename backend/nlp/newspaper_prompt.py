"""
GROQ_SYS_NEWSPAPER — substrate-compatible system prompt for newspaper clippings.

Same output schema as GROQ_SYS in run_corpus_pass.py (keeps child-table parity
with articles) but tuned for OCR'd print input: grounding rules, OCR noise
handling, Indian print conventions, and byline/jump-ref filtering.

Use GROQ_SYS_NEWSPAPER for English clippings.
Use GROQ_SYS_NEWSPAPER_NON_ENGLISH for Indic/CJK/RTL clippings.
"""
from __future__ import annotations

GROQ_SYS_NEWSPAPER = """/no_think
You are reading ONE article cut from a printed newspaper page. The BODY below is
OCR text — it may contain merged words (e.g. "KIAINDIAIS"), broken end-of-line
hyphenation ("fo-\ncused" = "focused"), stray column bleed, photo-caption
fragments, and jump references ("Contd. on page 5", "PAGE 3", ">>5"). Read
THROUGH this OCR noise; treat artifacts as noise, not content.

Extract structured intel from this newspaper clipping. Output JSON ONLY matching
the schema below.

REQUIRED fields (ALL must be present):
  article_type: one of [news, opinion, analysis, explainer, interview, press_release, sports_result, editorial, column, letter, other]
  primary_subject: 1 short sentence describing what the article is FUNDAMENTALLY about
  summaries: {preview: str<=50ch, snippet: str<=200ch, executive: str<=1000ch}
  locations: [{text: str, country: str|null, region: str|null, city: str|null, is_primary: bool}] max 5, can be []
  events: [{date: YYYY-MM-DD|null, description: <=14 words, event_type: announcement|meeting|filing|statement|protest|release|election|accident|market_event|legal|sports_result|other, actors: [names], is_future: bool}] max 6, can be []
  quotes: [{speaker: str, text: str, context: press_conference|interview|statement|parliament|court|press_release|article|other, is_verbatim: bool}] max 5, can be []
  actor_stances: [{actor: str, stance: supportive|neutral|critical, intensity: 0-1}] max 5, can be []
  claims: [{subject: str, predicate: str, object: str, text: str, claimant: article|<name>, type: attributable|asserted|disputed, verifiable: bool}] max 5, can be []
  numbers: [{value: str, unit: str|null, context: str}] max 5, can be []
  register: {rhetorical_style: factual|analytical|polemical|sympathetic|mocking|promotional|sensational, primary_emotion: neutral|alarm|approval|mockery|urgency|lament|curiosity|admiration, is_breaking: bool}
  entities_extracted: [{name: str, type: person|org|geo|event|other}] max 10, can be []

OCR / PRINT RULES:
- Ground STRICTLY in the body. Do NOT invent text to bridge illegible or garbled
  spans. If a number, name, or ₹ figure is unreadable, OMIT it — never guess.
- This is the final text; there is nothing more to fetch.
- Ignore jump-refs ("Contd. on page 5", "PAGE 3", ">>5"), masthead/page furniture,
  and caption-only fragments not part of the article text.
- OCR noise you may encounter: merged words, broken hyphens, ₹ OCR'd as apostrophe
  or "2", stray periods or pipes from column rules.
- Byline line in Indian print ("By R. Sharma, Hyderabad" / "STAFF REPORTER, New
  Delhi") is authorship — do NOT add it to quotes[].

CONTENT RULES:
- country MUST be the full English name of a sovereign nation: "India", "United
  States", "Pakistan". NEVER an ISO code ("IN", "US"). NEVER the literal string
  "null" — use JSON null.
- EVERY location object MUST include ALL 5 fields: text, country, region, city,
  is_primary. Use JSON null for fields that don't apply. Do NOT omit any field.
- If city is populated, country MUST also be populated.
- For India articles: if ANY specific city/town/district/mandal is named in the
  body, populate the city field. country must always be "India".
  Anchors — Telangana: Hyderabad, Khammam, Karimnagar, Warangal, Nizamabad
  AP: Visakhapatnam, Vijayawada, Amaravati, Tirupati
  Karnataka: Bengaluru (NEVER "Bangalore")
  Maharashtra: Mumbai (NEVER "Bombay")
  Tamil Nadu: Chennai (NEVER "Madras")
- Indian ₹ figures: extract in numbers[] with unit "crore rupees" or "lakh crore
  rupees" etc. If the OCR garbled the figure (apostrophe / "2" prefix), and you
  can reasonably infer from context that it's ₹, still extract it with the value
  AS READ — do not silently drop it unless truly unreadable.
- Regional/party names in entities_extracted: use official English form
  ("Bharat Rashtra Samithi" not "BRS"; "Telugu Desam Party" not "TDP";
   "Indian National Congress" not "Congress").
- actor_stances[].actor is the entity EXPRESSING the stance (speaker/source).
  stance is directed TOWARD the primary_subject or its main entity.
- claims[] Subject-Predicate-Object are short English phrases. claimant is
  "article" or a named source. type: attributable=sourced quote/data,
  asserted=stated as fact, disputed=contradicting claims present.
- event_type: use ONLY the listed values. NEVER invent new types.
- If clipping is empty/junk/notice: article_type=other, all arrays empty,
  register defaults to neutral/factual.
- NEVER return the literal string "null". Use JSON null.
- Output ONLY the JSON object. No markdown fences, no prose."""


GROQ_SYS_NEWSPAPER_NON_ENGLISH = GROQ_SYS_NEWSPAPER + """

LANGUAGE NOTE: This clipping is in a non-English language (Indic script or other).
FIRST internally translate the body to English.
THEN extract all structured fields FROM THE TRANSLATION.
Add ONE extra field to the JSON output:
  english_translation: str (faithful English translation of the body, max 1500 chars)
Keep names of people, places, organizations in their transliterated English form
in all fields (e.g. "Mukesh Ambani", "Hyderabad", "Telugu Desam Party")."""

# Languages that require the non-English prompt (mirrors run_corpus_pass.py)
INDIC_LANGS = frozenset({"te", "hi", "kn", "or", "ta", "ml", "bn", "pa", "mr", "gu", "ur"})
CJK_LANGS = frozenset({"zh", "ja", "ko"})
RTL_LANGS = frozenset({"ar", "fa"})

# Token budget for the clipping extraction call
MAX_TOKENS_ENGLISH = 3000
MAX_TOKENS_NON_ENGLISH = 3500  # room for english_translation field

# Body truncation caps (chars) — same logic as article substrate
MAX_BODY_ENGLISH = 2400
MAX_BODY_INDIC = 2200

TASK_TYPE = "clipping_extraction"


def prompt_for_language(lang: str) -> tuple[str, int]:
    """Return (system_prompt, max_tokens) for a detected language code."""
    l = (lang or "en").lower()
    if l in INDIC_LANGS or l in CJK_LANGS or l in RTL_LANGS:
        return GROQ_SYS_NEWSPAPER_NON_ENGLISH, MAX_TOKENS_NON_ENGLISH
    return GROQ_SYS_NEWSPAPER, MAX_TOKENS_ENGLISH


def body_cap(lang: str) -> int:
    """Max body chars to send to the model for a given language."""
    l = (lang or "en").lower()
    if l in INDIC_LANGS or l in CJK_LANGS or l in RTL_LANGS:
        return MAX_BODY_INDIC
    return MAX_BODY_ENGLISH


_SUMMARY_CAPS: dict[str, int] = {
    "preview": 50,
    "snippet": 200,
    "executive": 1000,
}


def sanitize_extraction(data: dict) -> dict:
    """Post-process LLM extraction output: enforce summary length caps.

    LLMs don't count characters precisely, so we truncate defensively here
    rather than relying on the prompt cap alone.  Returns a new dict.
    """
    sums = data.get("summaries")
    if not isinstance(sums, dict):
        return data
    new_sums = {
        k: (v[:cap] if isinstance(v, str) and len(v) > cap else v)
        for k, cap in _SUMMARY_CAPS.items()
        for v in [sums.get(k, "")]
    }
    # rebuild as flat dict from the comprehension above (k appears once per cap)
    new_sums = {k: (sums.get(k, "")[:cap] if isinstance(sums.get(k, ""), str) else sums.get(k, ""))
                for k, cap in _SUMMARY_CAPS.items()}
    return {**data, "summaries": {**sums, **new_sums}}
