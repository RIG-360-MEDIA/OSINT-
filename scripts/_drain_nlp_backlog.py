"""One-shot dedicated drainer for the NLP entity backlog (nlp_processed=FALSE).
Bypasses the contended 4-slot `nlp` Celery worker by running process_nlp_batch
synchronously in its own process. Newest-first (the task's own ORDER BY), so the
night-desk's recent articles re-acquire entities first. Self-terminates when the
backlog is empty. Run detached inside rig-backend."""
from backend.tasks.nlp_processor import process_nlp_batch

total = 0
empty_rounds = 0
while True:
    result = process_nlp_batch.apply().result or {}
    processed = int(result.get("processed", 0))
    skipped = int(result.get("skipped", 0))
    total += processed
    print(f"drain: +{processed} processed, {skipped} skipped (total {total})", flush=True)
    if processed == 0 and skipped == 0:
        empty_rounds += 1
        if empty_rounds >= 3:  # backlog drained — newcomers handled by the beat
            break
    else:
        empty_rounds = 0
print(f"DONE: drained {total} articles", flush=True)
