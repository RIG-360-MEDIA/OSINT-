"""Embedding stage: load sample.json, embed title+summary, save vectors + meta.

Uses paraphrase-multilingual-MiniLM-L12-v2 for speed + multilingual coverage
(handles Telugu/English/Hindi alignment). ~120MB model, ~30s on CPU for 100 articles.
"""
import json, os, sys, time
from pathlib import Path

HERE = Path(__file__).parent
SAMPLE = HERE / "sample.json"
OUT_EMB = HERE / "embeddings.npy"
OUT_META = HERE / "meta.json"

def main():
    t0 = time.time()
    with open(SAMPLE, encoding="utf-8") as f:
        rows = json.load(f)
    print(f"Loaded {len(rows)} articles in {time.time()-t0:.1f}s")

    from sentence_transformers import SentenceTransformer
    import numpy as np
    print("Loading model...")
    t0 = time.time()
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    print(f"Model loaded in {time.time()-t0:.1f}s, dim={model.get_sentence_embedding_dimension()}")

    texts = []
    for r in rows:
        title = (r.get("title") or "").strip()
        subj = (r.get("primary_subject") or "").strip()
        summ = (r.get("summary_executive") or "").strip()
        texts.append(f"{title}\nSubject: {subj}\n{summ}")

    print(f"Encoding {len(texts)} texts...")
    t0 = time.time()
    emb = model.encode(texts, batch_size=16, show_progress_bar=False,
                       convert_to_numpy=True, normalize_embeddings=True)
    print(f"Encoded in {time.time()-t0:.1f}s, shape={emb.shape}")

    np.save(OUT_EMB, emb)
    meta = [{"id": r["id"], "title": r["title"], "subject": r["primary_subject"],
             "summary": r["summary_executive"], "lang": r["language_detected"],
             "source": r["source"], "published_at": r["published_at"], "url": r.get("url")}
            for r in rows]
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT_EMB.name} + {OUT_META.name}")

if __name__ == "__main__":
    main()
