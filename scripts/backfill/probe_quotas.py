"""Probe GROQ_API_KEYS and CEREBRAS_API_KEYS for remaining token quotas.

For each key:
  1. Send a tiny request to a model
  2. Parse x-ratelimit-* response headers
  3. If 429, parse the body to extract daily TPD limit/used

Outputs a totals table:
  provider | keys | tpd_limit_total | tpd_used_total | tpd_remaining_total
"""
import os
import re
import asyncio
import json
from typing import Any
import httpx


GROQ_MODEL = "qwen/qwen3-32b"  # the model semantic_repass actually uses
CEREBRAS_MODEL = os.environ.get("PROBE_CEREBRAS_MODEL", "qwen-3-235b-a22b-instruct-2507")

TPD_RE = re.compile(
    r"on tokens per day \(TPD\): Limit (\d+), Used (\d+)(?:, Requested (\d+))?",
    re.IGNORECASE,
)


async def probe_groq(idx: int, key: str) -> dict[str, Any]:
    """Use a large `max_tokens` to force the 429 TPD body when org is near cap.

    Successful 200 responses also expose headers but Groq doesn't show TPD
    used/limit on success — only on 429. So we ask for a big budget; if the
    request fits, the org has spare capacity (we record the headers); if it
    doesn't, we get a 429 body with exact TPD numbers.
    """
    async with httpx.AsyncClient(timeout=20) as c:
        try:
            r = await c.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": "List 20 random words."}],
                    "max_tokens": 8000,  # big ask → forces TPD check
                },
            )
            h = r.headers
            row = {
                "idx": idx,
                "tail": key[-6:],
                "status": r.status_code,
                "rem_req_min": h.get("x-ratelimit-remaining-requests"),
                "rem_tok_min": h.get("x-ratelimit-remaining-tokens"),
                "reset_tok": h.get("x-ratelimit-reset-tokens"),
                "tpd_limit": None,
                "tpd_used": None,
            }
            if r.status_code == 429:
                body = r.text
                m = TPD_RE.search(body)
                if m:
                    row["tpd_limit"] = int(m.group(1))
                    row["tpd_used"] = int(m.group(2))
            elif r.status_code == 200:
                # Use the response's "x-ratelimit-remaining-tokens" header if available;
                # Groq doesn't expose remaining-TPD on successful calls. We mark unknown.
                pass
            elif r.status_code == 400:
                # likely organization_restricted
                try:
                    body = r.json().get("error", {})
                    row["err"] = body.get("message", "")[:60]
                except Exception:
                    row["err"] = r.text[:60]
            return row
        except Exception as e:
            return {"idx": idx, "tail": key[-6:], "status": "EXC", "err": str(e)[:60]}


async def probe_cerebras(idx: int, key: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as c:
        try:
            r = await c.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": CEREBRAS_MODEL,
                    "messages": [{"role": "user", "content": "List 20 random words."}],
                    "max_tokens": 8000,  # big ask → forces TPD check
                },
            )
            h = r.headers
            row = {
                "idx": idx,
                "tail": key[-6:],
                "status": r.status_code,
                # Cerebras header names — they expose both per-minute and per-day
                "rem_req_min": h.get("x-ratelimit-remaining-requests-minute") or h.get("x-ratelimit-remaining-requests"),
                "rem_tok_min": h.get("x-ratelimit-remaining-tokens-minute") or h.get("x-ratelimit-remaining-tokens"),
                "rem_req_day": h.get("x-ratelimit-remaining-requests-day"),
                "rem_tok_day": h.get("x-ratelimit-remaining-tokens-day"),
                "limit_tok_day": h.get("x-ratelimit-limit-tokens-day"),
                "tpd_limit": None,
                "tpd_used": None,
            }
            if r.status_code == 429:
                try:
                    body = r.text
                    m = TPD_RE.search(body)
                    if m:
                        row["tpd_limit"] = int(m.group(1))
                        row["tpd_used"] = int(m.group(2))
                    else:
                        row["err"] = body[:80]
                except Exception:
                    pass
            # Derive tpd_limit / tpd_used from headers when available
            if row.get("limit_tok_day") and row.get("rem_tok_day"):
                try:
                    lim = int(row["limit_tok_day"])
                    rem = int(row["rem_tok_day"])
                    row["tpd_limit"] = lim
                    row["tpd_used"] = lim - rem
                except (TypeError, ValueError):
                    pass
            return row
        except Exception as e:
            return {"idx": idx, "tail": key[-6:], "status": "EXC", "err": str(e)[:60]}


def fmt_int(n: int | None) -> str:
    if n is None:
        return "  ?"
    return f"{n:>10,}"


async def main() -> None:
    groq_keys = [k.strip() for k in os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]
    cere_keys = [k.strip() for k in os.environ.get("CEREBRAS_API_KEYS", "").split(",") if k.strip()]
    print(f"Configured: groq={len(groq_keys)}, cerebras={len(cere_keys)}\n")

    groq_rows = await asyncio.gather(*[probe_groq(i, k) for i, k in enumerate(groq_keys)])
    cere_rows = await asyncio.gather(*[probe_cerebras(i, k) for i, k in enumerate(cere_keys)])

    def print_table(title: str, rows: list[dict[str, Any]]) -> tuple[int, int, int]:
        print(f"\n=== {title} ({len(rows)} keys) ===")
        print(f"{'idx':>3}  {'tail':<7} {'st':>4}  {'rem_req/m':>10}  {'rem_tok/m':>10}  {'tpd_lim':>11}  {'tpd_used':>11}  {'tpd_rem':>11}  note")
        tot_lim = tot_used = known = 0
        for r in sorted(rows, key=lambda x: x.get("idx", 0)):
            lim = r.get("tpd_limit")
            used = r.get("tpd_used")
            rem_tpd = (lim - used) if (lim is not None and used is not None) else None
            note = ""
            if r.get("status") == 400 and r.get("err"):
                note = "DEAD: " + r["err"][:40]
            elif r.get("status") == "EXC":
                note = "EXC: " + r.get("err", "")[:40]
            elif r.get("status") == 429:
                note = "TPD-capped"
            elif r.get("status") == 200:
                note = "ALIVE"
            print(
                f"{r.get('idx',0):>3}  ...{r.get('tail','?'):<5} "
                f"{str(r.get('status','?')):>4}  "
                f"{str(r.get('rem_req_min') or '?'):>10}  "
                f"{str(r.get('rem_tok_min') or '?'):>10}  "
                f"{fmt_int(lim)}  {fmt_int(used)}  {fmt_int(rem_tpd)}  {note}"
            )
            if lim is not None and used is not None:
                tot_lim += lim
                tot_used += used
                known += 1
        return tot_lim, tot_used, known

    g_lim, g_used, g_known = print_table("GROQ", groq_rows)
    c_lim, c_used, c_known = print_table("CEREBRAS", cere_rows)

    print("\n" + "=" * 78)
    print("DAILY TOKEN QUOTA TOTALS (only keys with measurable headers/429 body)")
    print("=" * 78)
    print(f"{'provider':<10} {'keys_known':>11} {'tpd_limit':>15} {'tpd_used':>15} {'tpd_remaining':>15}")
    print(f"{'GROQ':<10} {g_known:>11} {g_lim:>15,} {g_used:>15,} {(g_lim - g_used):>15,}")
    print(f"{'CEREBRAS':<10} {c_known:>11} {c_lim:>15,} {c_used:>15,} {(c_lim - c_used):>15,}")
    print(f"{'TOTAL':<10} {g_known + c_known:>11} {(g_lim + c_lim):>15,} {(g_used + c_used):>15,} {((g_lim + c_lim) - (g_used + c_used)):>15,}")


if __name__ == "__main__":
    asyncio.run(main())
