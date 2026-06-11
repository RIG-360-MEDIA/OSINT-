"""Probe each Groq key separately to check if they share an org (= shared TPD)
or are independent (= 21x 500K = 10.5M total daily budget)."""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/app")
import httpx  # noqa: E402

from backend.nlp.groq_client import groq_manager  # noqa: E402


def main() -> int:
    print(f"Probing all {len(groq_manager.keys)} Groq keys...\n")
    print(f"{'#':<4} {'suffix':<8} {'status':<8} {'org_id':<42} {'used_today':<14} {'remaining_min':<8}")
    print("-" * 90)

    orgs_seen: set[str] = set()
    for i, key in enumerate(groq_manager.keys):
        try:
            r = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "qwen/qwen3-32b",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
                timeout=8,
            )
        except Exception as e:  # noqa: BLE001
            print(f"{i:<4} ...{key[-6:]:<5} EXC      {str(e)[:60]}")
            continue

        suffix = key[-6:]
        status = r.status_code
        rem_min = r.headers.get("x-ratelimit-remaining-tokens", "?")

        if status == 429:
            body = r.text[:400]
            org_m = re.search(r"organization `([^`]+)`", body)
            used_m = re.search(r"Used (\d+)", body)
            org = (org_m.group(1) if org_m else "?")
            used = used_m.group(1) if used_m else "?"
            orgs_seen.add(org)
            print(f"{i:<4} ...{suffix:<5} {status:<8} {org:<42} used={used:<10} {rem_min:<8}")
        elif status == 200:
            print(f"{i:<4} ...{suffix:<5} {status:<8} <ok>                                       FRESH         {rem_min:<8}")
        else:
            print(f"{i:<4} ...{suffix:<5} {status:<8} <other>  body={r.text[:80]}")

    print()
    print(f"=== Distinct orgs seen: {len(orgs_seen)} ===")
    for o in orgs_seen:
        print(f"  {o}")
    print()
    if len(orgs_seen) == 1:
        print("VERDICT: ALL keys share ONE org -> total daily budget = 500K, NOT 10.5M")
    elif len(orgs_seen) >= 5:
        print(f"VERDICT: {len(orgs_seen)} distinct orgs -> total daily budget ~= {len(orgs_seen)*500}K")
    return 0


if __name__ == "__main__":
    sys.exit(main())
