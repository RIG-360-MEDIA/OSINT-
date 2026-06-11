"""One-off: probe live Groq + Cerebras rate-limit headers (remaining daily quota)."""
import httpx

def hdr(h, *names):
    for n in names:
        v = h.get(n)
        if v is not None:
            return v
    return "?"

print("=== CEREBRAS (zai-glm-4.7) ===")
try:
    from backend.nlp.groq_client import _CEREBRAS_KEYS, _CEREBRAS_BASE, _BROWSER_UA
    for i, key in enumerate(_CEREBRAS_KEYS[:3]):
        try:
            r = httpx.post(_CEREBRAS_BASE, headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                "User-Agent": _BROWSER_UA,
            }, json={"model": "zai-glm-4.7", "messages": [{"role": "user", "content": "hi"}],
                     "max_tokens": 1, "temperature": 0, "reasoning_effort": "none"}, timeout=20)
            h = r.headers
            print(f"  key{i}: status={r.status_code} "
                  f"day_tokens={hdr(h,'x-ratelimit-remaining-tokens-day')}/{hdr(h,'x-ratelimit-limit-tokens-day')} "
                  f"day_req={hdr(h,'x-ratelimit-remaining-requests-day')}/{hdr(h,'x-ratelimit-limit-requests-day')} "
                  f"min_tokens={hdr(h,'x-ratelimit-remaining-tokens-minute')}/{hdr(h,'x-ratelimit-limit-tokens-minute')}")
        except Exception as e:
            print(f"  key{i}: ERROR {str(e)[:90]}")
except Exception as e:
    print("  cerebras import failed:", str(e)[:120])

print("=== GROQ (qwen/qwen3-32b) ===")
try:
    import backend.nlp.groq_client as gc
    # Try a few ways to find the groq keys
    keys = None
    for attr in ("_GROQ_KEYS", "GROQ_KEYS"):
        if hasattr(gc, attr):
            keys = list(getattr(gc, attr)); break
    if keys is None and hasattr(gc, "groq_manager"):
        gm = gc.groq_manager
        raw = getattr(gm, "keys", None)
        if raw:
            keys = [getattr(k, "key", None) or getattr(k, "api_key", None) or k for k in raw]
    if not keys:
        print("  could not locate groq keys")
    else:
        for i, key in enumerate(keys[:3]):
            try:
                r = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers={
                    "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                }, json={"model": "qwen/qwen3-32b", "messages": [{"role": "user", "content": "hi"}],
                         "max_tokens": 1, "temperature": 0}, timeout=20)
                h = r.headers
                print(f"  key{i}: status={r.status_code} "
                      f"day_tokens={hdr(h,'x-ratelimit-remaining-tokens')}/{hdr(h,'x-ratelimit-limit-tokens')} "
                      f"day_req={hdr(h,'x-ratelimit-remaining-requests')}/{hdr(h,'x-ratelimit-limit-requests')} "
                      f"reset_tokens={hdr(h,'x-ratelimit-reset-tokens')}")
            except Exception as e:
                print(f"  key{i}: ERROR {str(e)[:90]}")
except Exception as e:
    print("  groq probe failed:", str(e)[:120])
