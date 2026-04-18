from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db
from backend.nlp.groq_client import FAST_MODEL, call_groq, extract_json

logger = logging.getLogger(__name__)

onboarding_router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# ── Request models ────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    answer: str
    question_number: int
    previous_profile: dict = {}


class ConfirmRequest(BaseModel):
    role_type: str
    geo_primary: str
    geo_secondary: list[str] = []
    entities: list[dict] = []
    signal_priorities: dict = {}
    role_context: str = ""


# ── Questions ─────────────────────────────────────────────────────────────────

QUESTIONS = [
    {
        "id": 1,
        "text": "Start by telling me who you are and what you do. Don't hold back — the more you tell me about your world, the better I can serve you.",
        "extracts": ["role_type", "organisation", "role_context"],
    },
    {
        "id": 2,
        "text": "What people, organisations, places, or projects do you need to monitor most closely right now? These are the things you cannot afford to miss a development on.",
        "extracts": ["entities"],
    },
    {
        "id": 3,
        "text": "Where in the world does your work primarily happen? Tell me the geography that matters most — a country, a state, a city, or multiple places.",
        "extracts": ["geo_primary", "geo_secondary"],
    },
    {
        "id": 4,
        "text": "When you open your intelligence feed every morning, what would make you say 'this is exactly what I needed to know'? What kind of information would genuinely change how you act that day?",
        "extracts": ["signal_priorities"],
    },
    {
        "id": 5,
        "text": "What keeps you up at night? What is the scenario you are most worried could develop in the next 30 to 90 days that would seriously impact your work if you were not prepared for it?",
        "extracts": ["risk_signals"],
    },
]

EXTRACTION_SYSTEM = """Extract structured intelligence profile data from this conversation answer. Merge with existing profile — do not overwrite fields that already have good data unless the new answer provides better information.

Output JSON only. No markdown. No explanation. No extra fields.

{
  "role_type": "government|business|journalist|security|other or null",
  "organisation": "string or null",
  "geo_primary": "primary location string or null",
  "geo_secondary": ["list of secondary locations"],
  "entities": [
    {
      "name": "canonical entity name",
      "type": "person|organisation|place|scheme|topic",
      "why": "one sentence why monitoring"
    }
  ],
  "signal_priorities": {
    "POLITICS": 1-10,
    "GOVERNANCE": 1-10,
    "INFRASTRUCTURE": 1-10,
    "SECURITY": 1-10,
    "HEALTH": 1-10,
    "LEGAL": 1-10,
    "BUSINESS": 1-10,
    "FINANCE": 1-10,
    "INTERNATIONAL": 1-10,
    "TECHNOLOGY": 1-10,
    "AGRICULTURE": 1-10,
    "ENVIRONMENT": 1-10,
    "SOCIAL": 1-10,
    "SPORTS": 1-10,
    "OTHER": 1-10
  },
  "role_context": "2-3 sentence context for intelligence prompts"
}

Rules:
- Merge entities arrays (deduplicate by name)
- Keep existing non-null values unless new answer clearly updates them
- signal_priorities: infer from context, not just explicit statements
- If answer does not address a field, keep existing value (pass through)"""

FOLLOWUP_SYSTEM = """Generate ONE intelligent follow-up question based on what was just extracted from a user's answer. The question should deepen the intelligence profile.

Rules:
- Maximum 2 sentences
- Specific to what they revealed
- Conversational, not form-like
- Do not repeat what was already asked
- Output the question text ONLY"""

FALLBACK_FOLLOWUPS: dict[str, str] = {
    "government": "Which specific districts or officials within your jurisdiction do you watch most closely?",
    "business": "Which competitors or regulatory bodies should I monitor for you specifically?",
    "journalist": "Which public figures or organisations are central to your current investigations?",
    "security": "Which locations or organisations are your primary areas of concern right now?",
    "other": "What specific people or organisations are most central to your daily work?",
}

# Valid role_type values matching DB CHECK constraint
VALID_ROLE_TYPES = frozenset({"government", "business", "journalist", "security", "other"})

# Valid entity_type values matching DB CHECK constraint
VALID_ENTITY_TYPES = frozenset({"person", "organisation", "place", "scheme", "project", "topic"})


# ── Endpoints ─────────────────────────────────────────────────────────────────

@onboarding_router.get("/questions")
async def get_questions() -> dict:
    return {"questions": [{"id": q["id"], "text": q["text"]} for q in QUESTIONS]}


@onboarding_router.post("/extract")
async def extract_profile(
    req: ExtractRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Extract profile data from one answer. Merges with previous_profile.
    Returns updated profile + new entities + dynamic follow-up question.
    """
    question = next((q for q in QUESTIONS if q["id"] == req.question_number), None)
    if not question:
        raise HTTPException(status_code=400, detail="Invalid question number")

    user_msg = (
        f"Question asked: {question['text']}\n\n"
        f"User's answer: {req.answer}\n\n"
        f"Existing profile so far: {json.dumps(req.previous_profile)}"
    )

    try:
        extracted = await extract_json(
            system=EXTRACTION_SYSTEM,
            user=user_msg,
            task_type="profile_extraction",
        )
    except Exception as e:
        logger.error("Profile extraction failed for user %s: %s", user["id"], e)
        raise HTTPException(status_code=500, detail="Profile extraction failed")

    # Generate follow-up for questions 1–4
    followup: str | None = None
    if req.question_number < 5:
        try:
            followup = await call_groq(
                system=FOLLOWUP_SYSTEM,
                user=(
                    f"Question was: {question['text']}\n"
                    f"Answer was: {req.answer}\n"
                    f"Extracted: {json.dumps(extracted)}"
                ),
                task_type="classification",
                model=FAST_MODEL,
            )
            if not followup or len(followup.strip()) < 20:
                role = extracted.get("role_type", "other") or "other"
                followup = FALLBACK_FOLLOWUPS.get(role, FALLBACK_FOLLOWUPS["other"])
        except Exception:
            role = extracted.get("role_type", "other") or "other"
            followup = FALLBACK_FOLLOWUPS.get(role, FALLBACK_FOLLOWUPS["other"])

    existing_names = {
        e.get("name", "").lower()
        for e in req.previous_profile.get("entities", [])
    }
    new_entities = [
        e for e in extracted.get("entities", [])
        if e.get("name", "").lower() not in existing_names
    ]

    return {
        "profile": extracted,
        "new_entities": new_entities,
        "followup_question": followup,
        "question_number": req.question_number,
    }


@onboarding_router.post("/confirm")
async def confirm_profile(
    req: ConfirmRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Save confirmed profile to database. Creates user_profiles and user_entities rows.
    Upserts ghost row in users table first (Supabase UUID bridging).
    Triggers relevance scoring for the new user.
    """
    # Normalise role_type to valid DB value
    role_type = req.role_type.lower() if req.role_type else "other"
    if role_type not in VALID_ROLE_TYPES:
        role_type = "other"

    geo_primary = req.geo_primary or ""
    role_context = req.role_context or ""

    async with get_db() as db:
        # Ghost row: satisfy FK constraint for Supabase Auth users
        try:
            await db.execute(
                text("""
                    INSERT INTO users (id, email)
                    VALUES (:user_id, :email)
                    ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email
                """),
                {"user_id": user["id"], "email": user["email"]},
            )
        except Exception as e:
            logger.warning("Ghost row upsert skipped for %s: %s", user["id"], e)
            # Non-fatal if email unique conflict — row may already exist

        # Upsert user_profiles
        await db.execute(
            text("""
                INSERT INTO user_profiles (
                    user_id, raw_description, role_type, geo_primary,
                    geo_secondary, signal_priorities, role_context, updated_at
                ) VALUES (
                    :user_id, :raw_description, :role_type, :geo_primary,
                    :geo_secondary, :signal_priorities::jsonb, :role_context, NOW()
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    role_type         = EXCLUDED.role_type,
                    geo_primary       = EXCLUDED.geo_primary,
                    geo_secondary     = EXCLUDED.geo_secondary,
                    signal_priorities = EXCLUDED.signal_priorities,
                    role_context      = EXCLUDED.role_context,
                    updated_at        = NOW()
            """),
            {
                "user_id": user["id"],
                "raw_description": role_context,
                "role_type": role_type,
                "geo_primary": geo_primary,
                "geo_secondary": req.geo_secondary or [],
                "signal_priorities": json.dumps(req.signal_priorities),
                "role_context": role_context,
            },
        )

        # Replace entities
        await db.execute(
            text("DELETE FROM user_entities WHERE user_id = :user_id"),
            {"user_id": user["id"]},
        )

        for i, entity in enumerate(req.entities[:50]):
            entity_type = entity.get("type", "topic")
            if entity_type not in VALID_ENTITY_TYPES:
                entity_type = "topic"

            name = (entity.get("name") or "").strip()
            if not name:
                continue

            await db.execute(
                text("""
                    INSERT INTO user_entities (
                        user_id, canonical_name, entity_type, why_watching, priority
                    ) VALUES (
                        :user_id, :name, :type, :why, :priority
                    )
                    ON CONFLICT (user_id, canonical_name) DO NOTHING
                """),
                {
                    "user_id": user["id"],
                    "name": name,
                    "type": entity_type,
                    "why": entity.get("why", ""),
                    "priority": max(1, 10 - min(i, 9)),
                },
            )

        await db.commit()

    # Trigger relevance scoring (non-fatal)
    try:
        from backend.celery_app import app as celery_app

        async with get_db() as score_db:
            result = await score_db.execute(
                text("""
                    SELECT id FROM articles
                    WHERE nlp_processed = TRUE
                    AND nlp_confidence != 'error'
                    LIMIT 500
                """)
            )
            article_ids = [str(r.id) for r in result.fetchall()]

        if article_ids:
            celery_app.send_task(
                "tasks.score_relevance_batch",
                args=[article_ids],
                queue="relevance",
            )
            logger.info(
                "Triggered relevance scoring for new user %s: %d articles",
                user["id"],
                len(article_ids),
            )
    except Exception as e:
        logger.warning("Could not trigger relevance scoring: %s", e)

    return {
        "success": True,
        "user_id": user["id"],
        "entities_saved": len(req.entities),
    }


@onboarding_router.get("/status")
async def onboarding_status(
    user: dict = Depends(get_current_user),
) -> dict:
    """Check if user has completed onboarding."""
    async with get_db() as db:
        result = await db.execute(
            text("""
                SELECT user_id FROM user_profiles
                WHERE user_id = :user_id
                AND role_type IS NOT NULL
            """),
            {"user_id": user["id"]},
        )
        row = result.fetchone()
        return {"has_profile": row is not None}
