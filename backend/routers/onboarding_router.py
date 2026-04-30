from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_principal, get_current_user
from backend.database import get_db
from backend.nlp.groq_client import FAST_MODEL, call_groq, extract_json
from backend.rate_limiter import rate_limit

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

# Pages every new user gets access to on first profile confirm.
# Excludes 'admin' — only super_admin sees that. Kept in sync with
# scripts/migrations/021_rbac_and_impersonation.sql and KNOWN_PAGES in
# backend.auth.auth_middleware.
DEFAULT_PAGE_GRANTS: tuple[str, ...] = (
    "coverage",
    "clips",
    "cuttings",
    "threads",
    "signals",
    "documents",
    "brief",
    "analyst",
    "worldmonitor",
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@onboarding_router.get("/questions")
async def get_questions() -> dict:
    return {"questions": [{"id": q["id"], "text": q["text"]} for q in QUESTIONS]}


@onboarding_router.post(
    "/extract",
    dependencies=[Depends(rate_limit("onboarding_extract", max_calls=10))],
)
async def extract_profile(
    req: ExtractRequest,
    user: dict = Depends(get_current_principal),
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
    user: dict = Depends(get_current_principal),
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

    # Track non-fatal subsystem failures so the frontend can surface a warning
    # without blocking onboarding completion. (D-03)
    grants_warning: str | None = None

    async with get_db() as db:
        # Ghost row: satisfy FK constraint for Supabase Auth users.
        #
        # D-10: handle the (rare) case where another row holds this email
        # under a different Supabase id — e.g. a deleted-and-recreated auth
        # user. We surface a clean 409 instead of letting a unique-violation
        # cascade into a confusing 500 mid-onboarding.
        from sqlalchemy.exc import IntegrityError

        try:
            await db.execute(
                text("""
                    INSERT INTO users (id, email)
                    VALUES (:user_id, :email)
                    ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email
                """),
                {"user_id": user["id"], "email": user["email"]},
            )
        except IntegrityError as exc:
            # users.email is UNIQUE; a different id already holds this email.
            await db.rollback()
            logger.error(
                "Onboarding ghost-row email conflict: id=%s email=%s — %s",
                user["id"], user["email"], exc,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "email_already_owned",
                    "message": (
                        "This email is associated with a different account. "
                        "Contact support to resolve."
                    ),
                },
            ) from exc

        # Default page grants — idempotent. (D-03) Failures used to be silently
        # logged as warnings, which left users with no page access and no
        # diagnostic trail. Now we log at ERROR, count the failure, and pass
        # a `warning` field through to the frontend so the user sees a
        # "contact support" hint instead of a broken-but-silent app.
        for slug in DEFAULT_PAGE_GRANTS:
            try:
                await db.execute(
                    text("""
                        INSERT INTO user_page_access (user_id, page_slug)
                        VALUES (:user_id, :slug)
                        ON CONFLICT (user_id, page_slug) DO NOTHING
                    """),
                    {"user_id": user["id"], "slug": slug},
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Default page grant FAILED for user=%s slug=%s: %s",
                    user["id"], slug, exc,
                )
                grants_warning = (
                    "Account created, but default page access could not be "
                    "applied. An administrator will need to grant page access "
                    "before you can use the app."
                )
                # Don't break the loop — try every slug so we set as many as
                # possible. The warning surfaces to the frontend regardless.

        # Upsert user_profiles
        await db.execute(
            text("""
                INSERT INTO user_profiles (
                    user_id, raw_description, role_type, geo_primary,
                    geo_secondary, signal_priorities, role_context, updated_at
                ) VALUES (
                    :user_id, :raw_description, :role_type, :geo_primary,
                    :geo_secondary, CAST(:signal_priorities AS jsonb), :role_context, NOW()
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

            raw_name = (entity.get("name") or "").strip()
            if not raw_name:
                continue

            # Resolve alias/shorthand to canonical dictionary name
            try:
                canon_result = await db.execute(
                    text("""
                        SELECT canonical_name
                        FROM entity_dictionary
                        WHERE canonical_name ILIKE :name
                           OR :name ILIKE ANY(aliases::text[])
                        LIMIT 1
                    """),
                    {"name": raw_name},
                )
                canon_row = canon_result.fetchone()
                if canon_row and canon_row.canonical_name != raw_name:
                    resolved_name = canon_row.canonical_name
                    logger.info(
                        "Onboarding entity resolved: '%s' → '%s'",
                        raw_name,
                        resolved_name,
                    )
                else:
                    resolved_name = raw_name  # exact match or not in dict — store as-is
            except Exception as exc:
                logger.warning("Canonical lookup failed for '%s': %s", raw_name, exc)
                resolved_name = raw_name  # never block onboarding

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
                    "name": resolved_name,
                    "type": entity_type,
                    "why": entity.get("why", ""),
                    "priority": max(1, 10 - min(i, 9)),
                },
            )

        await db.commit()

    # D-04: bound the post-onboarding relevance backfill to a recent window
    # and a hard batch ceiling. Previously this enqueued every nlp-processed
    # article ever ingested — fine for one user, but with N concurrent
    # signups the `relevance` queue would back up for hours and starve
    # everyone's brief generation. The window + ceiling means worst-case
    # impact is bounded regardless of corpus size.
    BACKFILL_DAYS = int(os.getenv("ONBOARDING_BACKFILL_DAYS", "14"))
    MAX_BATCHES = int(os.getenv("ONBOARDING_BACKFILL_MAX_BATCHES", "20"))
    BATCH = 100

    try:
        from backend.celery_app import app as celery_app

        async with get_db() as score_db:
            backfill_result = await score_db.execute(
                text("""
                    SELECT id::text FROM articles
                    WHERE nlp_processed = TRUE
                      AND nlp_confidence != 'error'
                      AND collected_at > NOW() - (:days * INTERVAL '1 day')
                    ORDER BY collected_at DESC
                    LIMIT :hard_cap
                """),
                {"days": BACKFILL_DAYS, "hard_cap": MAX_BATCHES * BATCH},
            )
            all_ids = [r[0] for r in backfill_result.fetchall()]

        batches = 0
        for i in range(0, len(all_ids), BATCH):
            celery_app.send_task(
                "tasks.score_relevance_batch",
                args=[all_ids[i : i + BATCH]],
                queue="relevance",
            )
            batches += 1

        logger.info(
            "Post-onboarding backfill: %d articles (%dd window) in %d/%d batches for user %s",
            len(all_ids),
            BACKFILL_DAYS,
            batches,
            MAX_BATCHES,
            user["id"],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not trigger relevance backfill: %s", e)

    return {
        "success": True,
        "user_id": user["id"],
        "entities_saved": len(req.entities),
        "warning": grants_warning,  # None on success; string on D-03 partial failure
    }


@onboarding_router.get("/status")
async def onboarding_status(
    user: dict = Depends(get_current_principal),
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
