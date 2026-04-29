"""
Language detection and translation for article lead text.

Detection: langdetect
Translation: Groq (Indian languages) or deep-translator (all others)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Max chars sent to a translator per call. Google Translate hard-caps at
# ~5 000; Groq is comfortable up to several thousand. 4 500 stays under
# Google's wall and keeps Indian-language articles from being truncated to
# a teaser. Bumped from 2 000 in coverage audit C-10 (2026-04-28).
TRANSLATION_MAX_CHARS: int = 4500

INDIAN_LANGUAGES: frozenset[str] = frozenset({
    "hi", "ta", "te", "bn", "mr", "gu", "kn", "ml",
    "pa", "or", "ur", "as", "ne", "si",
})


_ENGLISH_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "from", "of", "for", "with", "by", "and",
    "or", "but", "as", "has", "have", "had", "will", "would", "can",
    "could", "should", "may", "might", "this", "that", "these", "those",
    "it", "its", "his", "her", "their", "our", "your", "said", "says",
    "after", "before", "during", "between", "over", "under", "into",
    "out", "up", "down", "about", "against", "near", "than", "then",
    "also", "no", "not", "any", "all", "some", "other", "more", "most",
})


def _looks_like_english(text: str) -> bool:
    """
    Reject Groq output that's still source-script OR is transliteration
    (all-ASCII but no common English words — e.g. "vyakti mrutadeham labhyam").
    """
    if not text or len(text.strip()) < 3:
        return False
    sample = text[:400]
    ascii_letters = sum(1 for c in sample if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in sample if c.isalpha())
    if total_letters == 0:
        return False
    if (ascii_letters / total_letters) < 0.7:
        return False

    words = [w.strip(".,!?:;\"'()[]").lower() for w in sample.split()]
    word_count = sum(1 for w in words if w.isalpha())
    if word_count <= 3:
        # Too short to demand a stopword — accept on script alone.
        return True
    has_stopword = any(w in _ENGLISH_STOPWORDS for w in words)
    return has_stopword


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
      English    → no translation, return as-is (capped at TRANSLATION_MAX_CHARS)
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

    # Unicode range fallback: Odia script U+0B00–U+0B7F
    # langdetect often misclassifies Odia as 'en' on short samples
    if detected == "en" or not detected:
        odia_chars = sum(1 for c in working_text[:100] if "\u0B00" <= c <= "\u0B7F")
        if odia_chars > 5:
            detected = "or"
            logger.info("Odia script detected via Unicode range check for article")

    # English — no translation needed
    if detected == "en":
        source = lead_text_original or title
        return "en", (source or "")[:TRANSLATION_MAX_CHARS]

    # Odia — route to Google Translate (Groq quality is unreliable for Odia)
    if detected == "or":
        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source="auto", target="english").translate(
                working_text[:TRANSLATION_MAX_CHARS]
            )
            return detected, (translated or working_text[:TRANSLATION_MAX_CHARS])
        except Exception as exc:
            logger.warning("Odia translation failed: %s — falling back to title", exc)
            return detected, title

    # Indian languages — Groq, with Google Translate fallback when Groq
    # returns transliteration / source-script echo (a known failure mode for
    # short headlines).
    if detected in INDIAN_LANGUAGES:
        groq_out: str | None = None
        try:
            from backend.nlp.groq_client import translate as groq_translate
            groq_out = await groq_translate(
                text=working_text[:TRANSLATION_MAX_CHARS],
                target_language="English",
            )
        except Exception as exc:
            logger.warning("Groq translation failed (%s): %s", detected, exc)

        if groq_out and _looks_like_english(groq_out):
            return detected, groq_out

        # Fallback: Google Translate via deep-translator.
        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(
                source="auto", target="english"
            ).translate(working_text[:TRANSLATION_MAX_CHARS])
            if translated and _looks_like_english(translated):
                return detected, translated
        except Exception as exc:
            logger.warning(
                "Google fallback failed (%s): %s", detected, exc,
            )

        return detected, groq_out or working_text[:TRANSLATION_MAX_CHARS]

    # All other languages — deep-translator
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(
            source="auto", target="english"
        ).translate(working_text[:TRANSLATION_MAX_CHARS])
        return detected, (translated or working_text[:TRANSLATION_MAX_CHARS])
    except Exception as exc:
        logger.warning("deep-translator failed (%s): %s", detected, exc)
        return detected, working_text[:TRANSLATION_MAX_CHARS]
