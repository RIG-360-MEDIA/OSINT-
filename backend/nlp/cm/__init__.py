"""
CM Page political-intelligence NLP package.

Public modules:
    cache         — TTL cache keyed by (user_id, state, window).
    coalitions    — per-state ruling/opposition party_kind resolution.
    stance        — stance classifier (Groq few-shot).
    speakers      — speaker NER (Groq extract_json).
    issues        — issue clustering (HDBSCAN over LaBSE embeddings).
    counter_narrative — RAG-grounded talking-point generator with cite-ID guardrail.
    dissent       — pairwise contradiction detection.
"""
