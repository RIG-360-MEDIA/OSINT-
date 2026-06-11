"""
Probe EVERY Groq + Cerebras key: live status + remaining quota.

Keys are masked (only last 4 chars shown). Each key is retried up to 3x
so the current Groq network flakiness doesn't mislabel a good key as dead.

Run inside the backend container (has keys + egress):
  ssh hetzner "docker exec -i rig-backend python3 -" < probe_quota_all.py
"""
import time
import httpx
import backend.nlp.groq_client as gc

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def hdr(h, *names):
    for n in names:
        v = h.get(n)
        if v is not None:
            return v
    return "?"


def classify(status, summary):
    if status == 200:
        summary["ok"] += 1
    elif status in (401, 403):
        summary["auth_fail"] += 1
    elif status == 429:
        summary["rate_limited"] += 1
    else:
        summary["other"] += 1


def probe(cli, url, key, payload, extra_headers=None):
    """Return (status, headers) or (None, None) after 3 connection retries."""
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    last = ""
    for _ in range(3):
        try:
            r = cli.post(url, headers=headers, json=payload)
            return r.status_code, r.headers
        except Exception as e:  # noqa: BLE001
            last = str(e)[:60]
            time.sleep(1.5)
    return None, last


# ── GROQ ─────────────────────────────────────────────────────────────
print("=== GROQ  (model qwen/qwen3-32b) ===")
gkeys = list(gc.groq_manager.keys)
now = time.time()
exh = getattr(gc.groq_manager, "_exhausted_until", {}) or {}
exh_idx = sorted(i for i, t in exh.items() if (t or 0) > now) if isinstance(exh, dict) else []
print(f"total_keys={len(gkeys)}  manager_marks_exhausted={len(exh_idx)} {exh_idx[:40]}")
print("-" * 72)
gsum = {"ok": 0, "auth_fail": 0, "rate_limited": 0, "conn_err": 0, "other": 0}
gpayload = {"model": "qwen/qwen3-32b",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1, "temperature": 0}
with httpx.Client(timeout=15) as cli:
    for i, key in enumerate(gkeys):
        tag = f"key{i:2d}[...{str(key)[-4:]}]"
        status, h = probe(cli, GROQ_URL, key, gpayload)
        if status is None:
            gsum["conn_err"] += 1
            print(f"{tag} CONN_ERR (3 tries): {h}")
            continue
        classify(status, gsum)
        print(f"{tag} status={status} "
              f"tokens_left={hdr(h,'x-ratelimit-remaining-tokens')}/{hdr(h,'x-ratelimit-limit-tokens')} "
              f"req_left={hdr(h,'x-ratelimit-remaining-requests')}/{hdr(h,'x-ratelimit-limit-requests')} "
              f"reset={hdr(h,'x-ratelimit-reset-tokens','x-ratelimit-reset-requests')}")
print("-" * 72)
print("GROQ SUMMARY:", " ".join(f"{k}={v}" for k, v in gsum.items()))

# ── CEREBRAS ─────────────────────────────────────────────────────────
print("\n=== CEREBRAS  (model zai-glm-4.7) ===")
try:
    ckeys = list(gc._CEREBRAS_KEYS)
    cbase = gc._CEREBRAS_BASE
    cua = getattr(gc, "_BROWSER_UA", "Mozilla/5.0")
    print(f"total_keys={len(ckeys)}")
    print("-" * 72)
    csum = {"ok": 0, "auth_fail": 0, "rate_limited": 0, "conn_err": 0, "other": 0}
    cpayload = {"model": "zai-glm-4.7",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1, "temperature": 0, "reasoning_effort": "none"}
    with httpx.Client(timeout=20) as cli:
        for i, key in enumerate(ckeys):
            tag = f"key{i:2d}[...{str(key)[-4:]}]"
            status, h = probe(cli, cbase, key, cpayload, {"User-Agent": cua})
            if status is None:
                csum["conn_err"] += 1
                print(f"{tag} CONN_ERR (3 tries): {h}")
                continue
            classify(status, csum)
            print(f"{tag} status={status} "
                  f"day_tokens={hdr(h,'x-ratelimit-remaining-tokens-day')}/{hdr(h,'x-ratelimit-limit-tokens-day')} "
                  f"day_req={hdr(h,'x-ratelimit-remaining-requests-day')}/{hdr(h,'x-ratelimit-limit-requests-day')} "
                  f"min_tokens={hdr(h,'x-ratelimit-remaining-tokens-minute')}")
    print("-" * 72)
    print("CEREBRAS SUMMARY:", " ".join(f"{k}={v}" for k, v in csum.items()))
except Exception as e:  # noqa: BLE001
    print("  cerebras probe failed:", str(e)[:120])
