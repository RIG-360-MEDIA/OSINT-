"""
Language detection and translation for article lead text.

Detection: langdetect
Translation: Groq (Indian languages) or deep-translator (all others)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

INDIAN_LANGUAGES: frozenset[str] = frozenset({
    "hi", "ta", "te", "bn", "mr", "gu", "kn", "ml",
    "pa", "or", "ur", "as", "ne", "si",
})


async def detect_and_translate(
    lead_text_original: str | None,
    title: str,
) -> tuple[str, str]:
    """
    Detect language of lead text and translate to English if needed.

    Returns (language_detected, lead_text_translated).

    Priority:
      1. Use lead_text_original if present and > 50 chars
      2. Fall back to title
    Translation routing:
      English    → no translation, return as-is (capped at 2000 chars)
      Indian     → Groq llama-3.1-8b-instant
      Other      → deep-translator GoogleTranslator
    Errors      → return original text, detected language still set
    """
    working_text = (
        lead_text_original
        if lead_text_original and len(lead_text_original) > 50
        else title
    )

    if not working_text:
        return "en", ""

    # Detect language
    detected = "en"
    try:
        import langdetect
        detected = langdetect.detect(working_text[:500])
    except Exception as exc:
        logger.warning("langdetect failed: %s", exc)

    # English — no translation needed
    if detected == "en":
        source = lead_text_original or title
        return "en", (source or "")[:2000]

    # Indian languages — Groq
    if detected in INDIAN_LANGUAGES:
        try:
            from backend.nlp.groq_client import translate as groq_translate
            translated = await groq_translate(
                text=working_text[:2000],
                target_language="English",
            )
            return detected, translated
        except Exception as exc:
            logger.warning("Groq translation failed (%s): %s", detected, exc)
            return detected, working_text[:2000]

    # All other languages — deep-translator
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(
            source="auto", target="english"
        ).translate(working_text[:2000])
        return detected, (translated or working_text[:2000])
    except Exception as exc:
        logger.warning("deep-translator failed (%s): %s", detected, exc)
        return detected, working_text[:2000]
