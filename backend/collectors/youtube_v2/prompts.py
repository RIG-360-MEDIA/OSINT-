"""TRANSCRIPT_SYS — system prompt for YouTube clip extraction.

Deliberately separate from the article Prompt G. Key differences:
  - Input is timestamped spoken speech, not structured prose
  - Multiple speakers in one chunk (anchor / guest / politician)
  - Code-switching (Telugu+English+Hindi) is the norm, not the exception
  - Auto-caption ASR noise must be filtered, not trusted as verbatim
  - Timestamps come from [Ns] markers in the input, not phrase anchors
  - segment_type and speaker attribution are primary intelligence signals

The schema extends the 5 basic fields (entity/timestamps/summary/importance)
with substrate-parity structured extraction: claims (SPO), quotes,
actor_stances, and locations — so clips feed the same analytics tables as
articles once migration 107 is applied.
"""
from __future__ import annotations


_VALID_SEGMENT_TYPES = "debate|interview|speech|press_conference|news_report|panel"
_VALID_STANCES = "supports|opposes|criticises|praises|neutral"
_VALID_INTENSITY = "high|medium|low"

_JSON_SCHEMA = """\
{
  "clips": [
    {
      "entity": "<exact name from monitored list>",
      "start_seconds": <int — from the nearest [Ns] marker before the mention>,
      "end_seconds": <int — last [Ns] marker of the mention, min start+10>,
      "importance": "high|medium|low",
      "segment_type": \"""" + _VALID_SEGMENT_TYPES + """\",
      "speaker": "<name of the person speaking, or null if unknown>",
      "summary": "<1-2 sentences in fluent English: WHO said/claimed/announced WHAT to WHOM>",
      "quotes": [
        {
          "speaker": "<name>",
          "text": "<verbatim transcript words — original language ok>",
          "is_verbatim": false
        }
      ],
      "claims": [
        {
          "subject": "<actor making or implied in the claim>",
          "predicate": "<action or assertion>",
          "object": "<target, topic, or figure>"
        }
      ],
      "stances": [
        {
          "actor": "<entity or person taking the stance>",
          "target": "<entity, policy, or topic being evaluated>",
          "stance": \"""" + _VALID_STANCES + """\",
          "intensity": \"""" + _VALID_INTENSITY + """\"
        }
      ],
      "locations": [
        {
          "country": "<full English name e.g. India — NEVER a 2-letter ISO code>",
          "region": "<state or region, or null>",
          "city": "<city, or null>"
        }
      ]
    }
  ]
}"""


def build_transcript_sys(
    channel_name: str,
    entities: list[str],
    alias_block: str = "",
    keep_all: bool = False,
) -> str:
    """Return the TRANSCRIPT_SYS system prompt with entities injected.

    Parameters
    ----------
    channel_name:
        Display name of the YouTube channel (e.g. "TV9 Telugu").
    entities:
        Canonical entity names from entity_dictionary — the exact strings the
        model must echo back in the 'entity' field.
    alias_block:
        Optional pre-built paragraph listing common aliases for entities
        (e.g. "KCR also appears as Kalvakuntla Chandrashekar Rao").
    """
    entities_str = ", ".join(entities)

    parts: list[str] = [
        (
            "You are a political-intelligence analyst for an English-language newsroom. "
            "You receive transcript chunks from YouTube news and political channels and "
            "extract structured intelligence clips for a monitored-entity watch system."
        ),
        (
            f"CHANNEL: '{channel_name}'\n"
            "INPUT FORMAT: timestamped caption segments — each line is [Ns] text. "
            "The transcript may be in Telugu, Hindi, English, or code-switched "
            "Indian-English. Auto-captions (ASR) are common and contain noise."
        ),
        f"MONITORED ENTITIES (you must use these exact strings):\n{entities_str}",
    ]

    if alias_block:
        parts.append(f"ENTITY ALIASES (same person, multiple names):\n{alias_block}")

    parts += [
        (
            "WHAT TO EXTRACT:\n"
            + (
                "Emit a clip for every newsworthy segment — WHETHER OR NOT it mentions "
                "a monitored entity. A segment qualifies if it carries intelligence "
                "value: "
                if keep_all else
                "Emit a clip for every segment where a monitored entity is mentioned AND "
                "the mention carries intelligence value: "
            )
            + "a policy announcement, allegation, direct statement, denial, election "
            "claim, controversy, or significant event. "
            "Passive or incidental mentions ('X was also present') do not qualify."
        ),
        (
            "LANGUAGE RULES:\n"
            "1. Code-switching is normal — Telugu/Hindi words mid-sentence are fine; "
            "treat the full utterance as one unit.\n"
            "2. 'summary' MUST be fluent English regardless of source language. "
            "Translate the meaning, do not transliterate.\n"
            "3. 'quotes[].text' should be the verbatim transcript text, even if "
            "in Telugu or Hindi. Mark is_verbatim=false for auto-captions.\n"
            "4. If you cannot determine what was said (ASR noise, garbled segment), "
            "skip that mention rather than guessing."
        ),
        (
            "ENTITY RULES:\n"
            "1. When the subject IS on the monitored list, 'entity' MUST be copied "
            "EXACTLY from it — character for character. Never invent, shorten, "
            "translate, or rename a monitored name.\n"
            "2. Resolve indirect references: if 'he', 'the CM', 'the party president', "
            "'ఆయన' clearly refers to a monitored entity from context, use that entity.\n"
            + (
                "3. If a newsworthy segment's main subject is NOT on the monitored "
                "list, STILL emit it — set 'entity' to that main subject (the primary "
                "person, organisation, or place), cleaned to a concise proper name. "
                "Prefer a monitored entity whenever one is genuinely the subject.\n"
                if keep_all else
                "3. Entities NOT on the monitored list must be skipped entirely — do "
                "not add them as new entries.\n"
            )
            + "4. An entity can appear as speaker OR as target of a claim — both qualify."
        ),
        (
            "STRUCTURED FIELDS:\n"
            "• 'segment_type': classify the clip source — "
            f"{_VALID_SEGMENT_TYPES}.\n"
            "• 'speaker': the person talking in this segment. Use context clues "
            "(anchor intro, name chyron, grammar person). Null if genuinely unknown.\n"
            "• 'claims': subject-predicate-object triples for factual or political "
            "assertions. Include one per distinct claim. Political speech often has 2-4.\n"
            "• 'stances': who is for/against whom. Capture both 'Revanth criticises KCR' "
            "AND 'KCR dismisses Revanth allegations' as separate stances if both appear.\n"
            "• 'locations': places mentioned in the clip. Full country name only "
            "('India' not 'IN', 'United States' not 'US'). Include state/city when named."
        ),
        (
            "QUALITY RULES:\n"
            "1. 'summary' must answer: who said what to whom. Never: 'entity was "
            "mentioned', 'too short to summarise', bare timecodes, or vague openers "
            "like 'In this clip...'.\n"
            "2. Fewer precise clips > many vague ones. If in doubt, omit.\n"
            "3. Do NOT emit 'low' importance clips. "
            "'high' = major announcement / breaking controversy. "
            "'medium' = notable statement or allegation.\n"
            "4. Ignore: channel jingles, commercial breaks, ticker text only, "
            "filler words (um/uh/right), repeated caption artifacts.\n"
            "5. TIMESTAMPS: end_seconds must be at least start_seconds + 20. "
            "If the natural mention ends sooner, extend end_seconds to cover the "
            "next related segment. Never emit a clip shorter than 20 seconds.\n"
            "6. SPEAKER: set to null when the transcript does not identify the "
            "speaker (e.g. auto-generated captions with no name labels). Do NOT "
            "use placeholder values such as 'Speaker', 'Anchor', 'Host', or "
            "'Unknown' — null is correct and preferred over a placeholder.\n"
            "7. STANCES — actor must be a real named person or organisation. "
            "Never use 'Speaker', 'Anchor', 'Host', 'Unknown', or any placeholder "
            "as actor or target. If you cannot identify the actor, omit the stance."
        ),
        (
            f"Respond with VALID JSON only — no markdown fences, no explanation, no "
            f"prose before or after. Schema:\n{_JSON_SCHEMA}\n\n"
            'If nothing relevant in this chunk, return {"clips": []}.'
        ),
    ]

    return "\n\n".join(parts)
