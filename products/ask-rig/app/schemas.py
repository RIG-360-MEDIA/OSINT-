"""Request/response models for the Ask-RIG API (validated at the boundary)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=25)
    languages: list[str] | None = Field(
        default=None,
        description="Restrict to article language_detected codes, e.g. ['en','te','hi'].",
    )
    answer: bool = Field(default=True, description="Generate an LLM answer (else retrieval only).")
    rerank: bool | None = Field(
        default=None,
        description="Override the cross-encoder reranker (None = server default). "
        "Slower but higher quality; on CPU it adds ~20s.",
    )
    web: bool = Field(default=False, description="Fuse live web results (Set 3) with the corpus.")
    rewrite: bool = Field(default=True, description="RAG-Fusion: expand the query into sharper variants.")
    detailed: bool = Field(default=True, description="Detailed, synthesised answer (vs terse cited).")


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(
        default_factory=list,
        description="Prior turns for follow-up context (most recent last).",
    )


class RetrievedDoc(BaseModel):
    id: str
    title: str | None
    snippet: str | None
    url: str | None
    published_at: datetime | None
    source_id: str | None
    language: str | None
    score: float
    vec_rank: int | None
    lex_rank: int | None


class EntityCandidate(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: str | None
    party: str | None
    state: str | None
    n_articles: int


class Citation(BaseModel):
    marker: str  # e.g. "S1"
    doc_id: str
    title: str | None
    url: str | None
    published_at: datetime | None
    language: str | None


class AskResponse(BaseModel):
    query: str
    answer: str | None
    faithful: bool
    citations: list[Citation]
    retrieved: list[RetrievedDoc]
    notes: str | None = None
    personalized: bool = False
    web_used: bool = False
    rewritten: list[str] = []  # query variants used (RAG-Fusion), for transparency
