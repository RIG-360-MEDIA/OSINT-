"""Probe each Cerebras key separately to see if same rotation bug affects it."""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")
import httpx  # noqa: E402

from backend.nlp.groq_client import _CEREBRAS_KEYS  # noqa: E402


def main() -> int:
    print(f"Probing all {len(_CEREBRAS_KEYS)} Cerebras keys...\n")
    print(f"{'#':<4} {'suffix':<10} {'status':<8} {'remaining_tok_day':<18} {'limit_tok_day':<14} {'pct_used':<10}")
    print("-" * 80)

    drained: list[int] = []
    fresh: list[int] = []
    for i, key in enumerate(_CEREBRAS_KEYS):
        try:
            r = httpx.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "qwen-3-235b-a22b-instruct-2507",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
                timeout=8,
            )
        except Exception as e:  # noqa: BLE001
            print(f"{i:<4} ...{key[-6:]:<7} EXC      {str(e)[:50]}")
            continue

        status = r.status_code
        suffix = key[-6:]
        rem_day = r.headers.get("x-ratelimit-remaining-tokens-day", "?")
        lim_day = r.headers.get("x-ratelimit-limit-tokens-day", "?")
        pct = "?"
        try:
            pct_f = 100.0 * (1 - int(rem_day) / int(lim_day))
            pct = f"{pct_f:.1f}%"
            if pct_f >= 95:
                drained.append(i)
            else:
                fresh.append(i)
        except Exception:
            pass
        print(f"{i:<4} ...{suffix:<7} {status:<8} {rem_day:<18} {lim_day:<14} {pct:<10}")

    print()
    print(f"=== Summary ===")
    print(f"Total keys: {len(_CEREBRAS_KEYS)}")
    print(f"Fresh (<95% used): {len(fresh)}  indexes={fresh[:10]}")
    print(f"Drained (≥95% used): {len(drained)}  indexes={drained}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
