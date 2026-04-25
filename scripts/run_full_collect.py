"""One-shot: fire the full govt collector synchronously across every active source."""
from __future__ import annotations

import asyncio
import sys
import time

from backend.tasks.govt_task import _collect_govt_docs


def main() -> None:
    started = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] starting full collection...", flush=True)
    try:
        result = asyncio.run(_collect_govt_docs())
        elapsed = int(time.time() - started)
        print(f"[{time.strftime('%H:%M:%S')}] DONE in {elapsed}s: {result}", flush=True)
    except Exception as exc:  # noqa: BLE001
        elapsed = int(time.time() - started)
        print(f"[{time.strftime('%H:%M:%S')}] FAILED after {elapsed}s: {exc}", flush=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
