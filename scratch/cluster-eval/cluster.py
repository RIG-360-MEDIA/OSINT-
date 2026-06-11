"""Stage 2: kNN + LLM-as-judge + connected-component clustering.

Cerebras llama-3.3-70b, OpenAI-compatible. Round-robin across N keys.
Caches successful judgments in judgments_cache.jsonl so re-runs only fill gaps.
"""
import os, json, time, asyncio
from itertools import cycle
from pathlib import Path
import numpy as np
import httpx

HERE = Path(__file__).parent
EMB = HERE / "embeddings.npy"
META = HERE / "meta.json"
CACHE = HERE / "judgments_cache.jsonl"
OUT = HERE / "clusters.json"

SIM_FLOOR = 0.50
TOP_K = 10
LLM_CONCURRENCY = 6

MODEL = "qwen-3-235b-a22b-instruct-2507"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

JUDGE_PROMPT = """You are clustering news articles into stories. Two articles are the SAME STORY only if they describe the same specific event/incident/announcement (e.g., two outlets covering the same press conference, the same protest, the same court hearing, or different days of the same unfolding crisis).

They are DIFFERENT STORIES if they share a topic, person, or location but describe distinct events (e.g., two different KCR speeches, two unrelated road accidents, the same minister at different events).

Output exactly one line: `SAME: <short reason>` or `DIFFERENT: <short reason>`. When in doubt, say DIFFERENT.

ARTICLE A
Source: {sa}  |  Lang: {la}
Title: {ta}
Subject: {ga}
Summary: {ua}

ARTICLE B
Source: {sb}  |  Lang: {lb}
Title: {tb}
Subject: {gb}
Summary: {ub}
"""

def load_cache():
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                r = json.loads(line)
                cache[r["pair"]] = r
            except Exception:
                continue
    return cache

def append_cache(rec):
    with open(CACHE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

async def judge_pair(client, sem, key_cycle, A, B, pair_key):
    async with sem:
        prompt = JUDGE_PROMPT.format(
            sa=A["source"], la=A["lang"], ta=A["title"], ga=A["subject"], ua=A["summary"][:600],
            sb=B["source"], lb=B["lang"], tb=B["title"], gb=B["subject"], ub=B["summary"][:600],
        )
        for attempt in range(5):
            key = next(key_cycle)
            try:
                r = await client.post(CEREBRAS_URL, headers={"Authorization": f"Bearer {key}"},
                                      json={"model": MODEL, "temperature": 0, "max_tokens": 80,
                                            "messages": [{"role": "user", "content": prompt}]},
                                      timeout=30)
                if r.status_code in (429, 503):
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                txt = r.json()["choices"][0]["message"]["content"].strip()
                # strip <think>...</think> if present
                if "</think>" in txt:
                    txt = txt.split("</think>", 1)[1].strip()
                verdict = "SAME" if txt.upper().lstrip().startswith("SAME") else "DIFFERENT"
                return {"pair": pair_key, "verdict": verdict, "reason": txt[:300]}
            except Exception as e:
                if attempt == 4:
                    return {"pair": pair_key, "verdict": "ERROR", "reason": str(e)[:200]}
                await asyncio.sleep(0.5 * (attempt + 1))
        return {"pair": pair_key, "verdict": "ERROR", "reason": "max retries"}

async def main():
    keys_env = os.environ.get("CEREBRAS_API_KEYS", "")
    keys = [k.strip() for k in keys_env.split(",") if k.strip()]
    assert keys, "Set CEREBRAS_API_KEYS env var"
    print(f"Loaded {len(keys)} Cerebras keys")

    emb = np.load(EMB)
    with open(META, encoding="utf-8") as f:
        meta = json.load(f)
    N = len(meta)
    print(f"Loaded {N} articles, emb shape {emb.shape}")

    sim = emb @ emb.T
    np.fill_diagonal(sim, -1)
    pair_set = set()
    for i in range(N):
        nbr = np.argsort(-sim[i])[:TOP_K]
        for j in nbr:
            if sim[i, j] < SIM_FLOOR: break
            a, b = (i, int(j)) if i < j else (int(j), i)
            pair_set.add((a, b))
    pairs = sorted(pair_set)
    print(f"Candidate pairs: {len(pairs)}")

    cache = load_cache()
    pending = [(i, j) for (i, j) in pairs
               if cache.get(f"{i}-{j}", {}).get("verdict") in (None, "ERROR")]
    print(f"Cached good judgments: {len(cache) - sum(1 for v in cache.values() if v.get('verdict')=='ERROR')}")
    print(f"Pending (uncached or errored): {len(pending)}")

    if pending:
        sem = asyncio.Semaphore(LLM_CONCURRENCY)
        key_cycle = cycle(keys)
        t0 = time.time()
        async with httpx.AsyncClient() as client:
            tasks = [judge_pair(client, sem, key_cycle, meta[i], meta[j], f"{i}-{j}")
                     for (i, j) in pending]
            done = 0
            for fut in asyncio.as_completed(tasks):
                rec = await fut
                cache[rec["pair"]] = rec
                append_cache(rec)
                done += 1
                if done % 25 == 0:
                    print(f"  ...judged {done}/{len(pending)} in {time.time()-t0:.1f}s")
        print(f"Done judging in {time.time()-t0:.1f}s")

    # Tally + cluster
    same_count = err_count = 0
    edges = []
    for (i, j) in pairs:
        v = cache[f"{i}-{j}"]["verdict"]
        if v == "SAME":
            edges.append((i, j)); same_count += 1
        elif v == "ERROR":
            err_count += 1
    print(f"SAME edges: {same_count} | ERRORs: {err_count} | DIFFERENT: {len(pairs)-same_count-err_count}")

    parent = list(range(N))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    for i, j in edges: union(i, j)
    groups = {}
    for idx in range(N):
        groups.setdefault(find(idx), []).append(idx)
    clusters = sorted(groups.values(), key=lambda g: -len(g))
    print(f"Clusters: {len(clusters)} | multi-article: {sum(1 for c in clusters if len(c)>1)} | singletons: {sum(1 for c in clusters if len(c)==1)}")
    print(f"Top sizes: {[len(c) for c in clusters[:10]]}")

    judgments = {k: v for k, v in cache.items() if k in {f"{i}-{j}" for i,j in pairs}}
    # attach sim back
    for k in judgments:
        i, j = map(int, k.split("-"))
        judgments[k]["sim"] = float(sim[i, j])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"clusters": clusters, "edges": edges, "judgments": judgments,
                   "model": MODEL, "sim_floor": SIM_FLOOR, "top_k": TOP_K,
                   "n_articles": N}, f, indent=2)
    print(f"Wrote {OUT.name}")

if __name__ == "__main__":
    asyncio.run(main())
