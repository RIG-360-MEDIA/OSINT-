# backend/tasks package — all pipeline tasks
from backend.tasks.collector_tasks import (  # noqa: F401
    collect_html,
    collect_rss,
    generate_all_briefs,
    reset_groq_keys,
)
from backend.tasks.nlp_processor import process_nlp_batch as process_nlp_batch  # noqa: F401
from backend.tasks.relevance_task import score_relevance_batch as score_relevance_batch  # noqa: F401
from backend.tasks.backfill_task import score_unscored_articles as score_unscored_articles  # noqa: F401
from backend.tasks.dict_reload_task import check_entity_dict_version as check_entity_dict_version  # noqa: F401
from backend.tasks.thread_task import (  # noqa: F401
    assign_new_article_threads,
    nightly_thread_recluster,
)
from backend.tasks.youtube_task import collect_youtube as collect_youtube  # noqa: F401
from backend.tasks.govt_task import collect_govt_documents as collect_govt_documents  # noqa: F401
from backend.tasks.govt_relevance_task import (  # noqa: F401
    score_govt_doc_for_all_users,
    score_govt_doc_relevance,
)
from backend.tasks.govt_doctor_task import govt_collection_doctor as govt_collection_doctor  # noqa: F401
from backend.tasks.newspaper_task import collect_newspapers as collect_newspapers  # noqa: F401
