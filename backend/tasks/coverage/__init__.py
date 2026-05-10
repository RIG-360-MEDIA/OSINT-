"""
Celery task package for /coverage/articles analytics.

Tasks:
    refresh_user_cards          (daily 01:30 UTC)
    pick_breaking_per_user      (every 60 min)
    refresh_contradictions      (daily 04:30 UTC)
    refresh_top_stories         (every 6h)
    refresh_coverage_gaps       (daily 05:00 UTC)
    evaluate_notification_rules (every 15 min)
    extract_claims_quotes_for_article (incremental, fired by NLP batch)
"""
from backend.tasks.coverage.user_cards_task import (  # noqa: F401
    refresh_user_cards,
    retry_unrefreshed_cards,
)
from backend.tasks.coverage.spawn_sub_cards_task import spawn_sub_cards  # noqa: F401
# pick_breaking_per_user replaces the old DBSCAN cluster pipeline.
from backend.tasks.coverage.pick_breaking_per_user_task import (  # noqa: F401
    pick_breaking_per_user,
)
from backend.tasks.coverage.contradictions_task import refresh_contradictions  # noqa: F401
from backend.tasks.coverage.top_stories_task import refresh_top_stories  # noqa: F401
from backend.tasks.coverage.coverage_gaps_task import refresh_coverage_gaps  # noqa: F401
from backend.tasks.coverage.notifications_task import evaluate_notification_rules  # noqa: F401
from backend.tasks.coverage.claims_quotes_task import (  # noqa: F401
    extract_claims_quotes_for_article,
    extract_pending_claims_quotes,
    translate_pending_quotes,
)
