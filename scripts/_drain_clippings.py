"""One-shot: drain ALL pending clippings through the substrate enrichment (catch-up after
the periodic drain stalled). Loops _drain(50) until the pending queue is empty. The LLM pool
is rate-limited today (qwen3 TPD / gpt-oss TPM dry), so this is slow but resilient — the pool
retries until a key/model has headroom. Run detached."""
import asyncio
from backend.tasks.clipping_enrich import _drain


async def go():
    total = 0
    while True:
        r = await _drain(50)
        total += r.get("enriched", 0)
        print(f"drained so far: {total} (last batch {r})", flush=True)
        if r.get("enriched", 0) == 0 and r.get("failed", 0) == 0:
            break
    print(f"DONE total enriched {total}", flush=True)


asyncio.run(go())
