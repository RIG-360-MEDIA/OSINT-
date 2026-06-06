# backend/tasks package — all pipeline tasks
from backend.tasks.collector_tasks import (  # noqa: F401
    collect_html,
    collect_rss,
    reset_groq_keys,
)
from backend.tasks.nlp_processor import process_nlp_batch as process_nlp_batch  # noqa: F401
from backend.tasks.dict_reload_task import check_entity_dict_version as check_entity_dict_version  # noqa: F401
from backend.tasks.newspaper_task import collect_newspapers as collect_newspapers  # noqa: F401
