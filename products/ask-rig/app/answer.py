"""Compose a cited answer from retrieved docs, then enforce the cite-ID guardrail.

The guardrail is the whole point. In news the deadly failure mode is *confident
wrongness*, so every ``[S#]`` the model emits must resolve to a real retrieved
doc; any that doesn't is stripped and the answer is flagged ``faithful=False``.
All functions here are pure and unit-tested except ``answer_question`` (calls LLM).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.llm import LLMProvider
from app.schemas import Citation, RetrievedDoc

_CITE_RE = re.compile(r"\[S(\d+)\]")
_REFUSAL = "The corpus doesn't have enough on this yet."

_SYSTEM = (
    "You are RIG, an OSINT analyst. Answer ONLY from the numbered SOURCES provided. "
    "After every factual sentence, cite the source(s) inline like [S1] or [S2][S3]. "
    "Use ONLY source numbers that exist in the list. Do NOT use outside knowledge. "
    "Some sources may be in Telugu, Hindi or Tamil — read them and use them. "
    "If several sources are relevant, synthesize what they collectively report — "
    "partial or developing coverage is fine; state plainly if the picture is limited. "
    f'Reply exactly "{_REFUSAL}" ONLY if NONE of the sources relate to the question. '
    "Be concise and neutral."
)

DEBATE_SYSTEM = (
    "You are RIG, a neutral analyst. From ONLY the numbered SOURCES, present the "
    "strongest case FOR and the strongest case AGAINST the subject. Write two short "
    "labelled paragraphs — 'For:' then 'Against:'. Cite every claim inline with [S#]. "
    "Use ONLY source numbers that exist in the list; no outside knowledge. If the "
    "sources support only one side, say so explicitly for the other side."
)

SIGNIFICANCE_SYSTEM = (
    "You are RIG, an analyst. From ONLY the numbered SOURCES, explain WHY THIS MATTERS "
    "in 3-4 sentences: what is at stake, who is affected, and what may happen next. "
    "Cite every factual sentence with [S#]. No outside knowledge; if the sources do "
    "not say, do not speculate."
)

BRIEF_SYSTEM = (
    "You are RIG. Write a concise intelligence brief from ONLY the numbered SOURCES: "
    "3-6 short bullet points, each a distinct key development, each cited inline with "
    "[S#]. Lead with the most important. Use ONLY source numbers in the list; no "
    "outside knowledge. Be factual and neutral."
)

# Detailed mode — Claude-grade depth, but grounded and verifiable. This is the
# product's signature answer: thorough, well-organised, synthesised.
DETAILED_SYSTEM = (
    "You are RIG, a senior intelligence analyst writing for a reader who wants DEPTH and "
    "CLARITY. Answer the QUESTION thoroughly using ONLY the numbered SOURCES.\n\n"
    "Write a complete, well-structured answer:\n"
    "- Open with a direct 1-2 sentence answer to the question.\n"
    "- Then develop it in clear paragraphs: the key facts, the context behind them, the "
    "different angles or sides, and what it means / what may follow.\n"
    "- Use short bold sub-headers when the answer spans multiple themes.\n"
    "- Be specific: names, numbers, dates, and direct quotes when the sources give them.\n"
    "- SYNTHESISE across sources into a coherent narrative; do not just list them.\n\n"
    "Grounding rules (non-negotiable — this is what makes us better than a generic chatbot):\n"
    "- Use ONLY facts present in the SOURCES. Never invent or use outside knowledge.\n"
    "- Cite the supporting source(s) for each major claim inline like [S1] or [S2][S3], but keep "
    "the prose flowing — citations support, they don't interrupt. Not every sentence needs one; "
    "every factual claim must be traceable to a source.\n"
    "- If the sources are thin on part of the question, say so briefly rather than padding or guessing.\n"
    "Be authoritative, neutral, and genuinely useful."
)


def build_user_prompt(query: str, docs: list[RetrievedDoc]) -> str:
    lines = ["SOURCES:"]
    for i, doc in enumerate(docs, start=1):
        date = doc.published_at.date().isoformat() if doc.published_at else "n.d."
        lang = (doc.language or "?").upper()
        lines.append(
            f"[S{i}] ({lang}, {date}) {doc.title or ''}\n"
            f"    {doc.snippet or ''}\n"
            f"    {doc.url or ''}"
        )
    lines.append(f"\nQUESTION: {query}\n\nAnswer with inline [S#] citations:")
    return "\n".join(lines)


def used_markers(answer_text: str) -> list[int]:
    return sorted({int(m) for m in _CITE_RE.findall(answer_text)})


def validate_citations(answer_text: str, n_docs: int) -> tuple[bool, list[int]]:
    """Return ``(faithful, invalid_markers)``.

    Faithful = the model refused, OR it used >=1 citation and none are out of range.
    """
    used = used_markers(answer_text)
    invalid = [m for m in used if m < 1 or m > n_docs]
    refused = _REFUSAL.lower()[:30] in answer_text.lower()
    faithful = refused or (len(used) > 0 and not invalid)
    return faithful, invalid


def strip_invalid_markers(answer_text: str, n_docs: int) -> str:
    return _CITE_RE.sub(
        lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_docs else "", answer_text
    )


def to_citations(answer_text: str, docs: list[RetrievedDoc]) -> list[Citation]:
    cites: list[Citation] = []
    for marker in used_markers(answer_text):
        if 1 <= marker <= len(docs):
            doc = docs[marker - 1]
            cites.append(
                Citation(
                    marker=f"S{marker}",
                    doc_id=doc.id,
                    title=doc.title,
                    url=doc.url,
                    published_at=doc.published_at,
                    language=doc.language,
                )
            )
    return cites


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    faithful: bool
    citations: list[Citation]
    notes: str | None


def answer_with_system(
    llm: LLMProvider, system: str, query: str, docs: list[RetrievedDoc]
) -> AnswerResult:
    """Generate a cited answer under a custom system prompt, with the same cite-ID
    guardrail (used by /ask, debate, significance — all share the faithfulness check)."""
    if not docs:
        return AnswerResult(_REFUSAL, True, [], "no documents retrieved")
    raw = llm.complete(system, build_user_prompt(query, docs))
    faithful, invalid = validate_citations(raw, len(docs))
    clean = strip_invalid_markers(raw, len(docs)) if invalid else raw
    if faithful:
        notes = None
    elif invalid:
        notes = f"unfaithful: invalid citations {invalid} (stripped)"
    else:
        notes = "unfaithful: answer had no citations"
    return AnswerResult(clean, faithful, to_citations(clean, docs), notes)


def answer_question(llm: LLMProvider, query: str, docs: list[RetrievedDoc]) -> AnswerResult:
    return answer_with_system(llm, _SYSTEM, query, docs)
