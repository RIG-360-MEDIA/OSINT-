"""Probe each GROQ key in GROQ_API_KEYS for liveness.

Output:
  ALIVE key[idx] ...tail  status=200  -
  RATE  key[idx] ...tail  status=429  Rate limit reached ...
  DEAD  key[idx] ...tail  status=400  Organization has been restricted ...
"""
import os
import asyncio
import httpx


async def probe(idx: int, key: str) -> tuple[int, str, str, str]:
    async with httpx.AsyncClient(timeout=15) as c:
        try:
            r = await c.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": "ok"}],
                    "max_tokens": 2,
                },
            )
            if r.status_code == 200:
                return idx, "OK", "-", key[-6:]
            body = r.json().get("error", {})
            msg = body.get("message", "")[:120]
            return idx, str(r.status_code), msg, key[-6:]
        except Exception as e:  # noqa: BLE001
            return idx, "EXC", str(e)[:80], key[-6:]


async def main() -> None:
    keys = [k.strip() for k in os.environ["GROQ_API_KEYS"].split(",") if k.strip()]
    print(f"Total Groq keys configured: {len(keys)}\n")
    res = await asyncio.gather(*[probe(i, k) for i, k in enumerate(keys)])
    res.sort()
    alive = rate = dead = err = 0
    for idx, st, msg, tail in res:
        if st == "OK":
            marker, alive = "ALIVE", alive + 1
        elif st == "429":
            marker, rate = "RATE ", rate + 1
        elif "restricted" in msg.lower():
            marker, dead = "DEAD ", dead + 1
        else:
            marker, err = "ERR  ", err + 1
        print(f"{marker} key[{idx:2d}] ...{tail}  status={st}  {msg}")
    print(f"\nSummary: alive={alive}  rate-limited={rate}  dead={dead}  other_err={err}")


if __name__ == "__main__":
    asyncio.run(main())
