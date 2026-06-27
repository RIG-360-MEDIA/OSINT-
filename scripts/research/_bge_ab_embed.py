"""_bge_ab_embed.py — BGE-M3 A/B Step 2: embed haystack + queries on GPU.

Run on TRIJYA-8 (RTX 4090) AFTER copying bge_ab_haystack.jsonl + bge_ab_queries.json here.

Outputs (same directory as input files):
  bge_ab_emb_titlelead.npy   — (N, 1024) float32, native title+lead recipe
  bge_ab_emb_titleonly.npy   — (N, 1024) float32, title-only recipe
  bge_ab_emb_queries.npy     — (Q, 1024) float32, query embeddings (BGE-M3)
  bge_ab_emb_labse.npy       — (N, 1024) float32, LaBSE embeddings from haystack JSON
  bge_ab_id_order.json        — ordered list of article IDs (matches row order of .npy files)

Usage:
  python _bge_ab_embed.py [--data-dir <path>]
  Default data-dir: same directory as this script.
"""
from __future__ import annotations
import argparse, json, os, sys, time
import numpy as np

DATA_DIR_DEFAULT = os.path.dirname(os.path.abspath(__file__))
MAX_TOKENS = 1024  # BGE-M3 native context


def ensure_packages() -> None:
    try:
        import FlagEmbedding  # noqa: F401
    except ImportError:
        print("installing FlagEmbedding + torch...", flush=True)
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "FlagEmbedding", "torch", "--quiet"])


def load_haystack(data_dir: str) -> tuple[list[str], list[str], list[str], list[list[float]]]:
    """Returns (ids, texts_titlelead, texts_titleonly, labse_embs)."""
    path = os.path.join(data_dir, "bge_ab_haystack.jsonl")
    ids, titlelead, titleonly, labse = [], [], [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            ids.append(r["id"])
            title = (r.get("title") or "").strip()
            lead  = (r.get("lead")  or "").strip()
            text_tl = (title + "\n\n" + lead).strip() if lead else title
            titlelead.append(text_tl[:4000])   # ~1024 tokens in chars
            titleonly.append(title[:500])
            labse.append(r["labse_emb"])
    return ids, titlelead, titleonly, labse


def load_queries(data_dir: str) -> tuple[list[str], list[str]]:
    path = os.path.join(data_dir, "bge_ab_queries.json")
    with open(path, encoding="utf-8") as f:
        qs = json.load(f)
    return [q["cluster_id"] for q in qs], [q["query_text"] for q in qs]


def embed_bge(texts: list[str], label: str) -> np.ndarray:
    from FlagEmbedding import BGEM3FlagModel
    print(f"  loading BAAI/bge-m3 for '{label}'...", flush=True)
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    print(f"  embedding {len(texts)} texts ({label})...", flush=True)
    t0 = time.time()
    out = model.encode(
        texts,
        batch_size=32,
        max_length=MAX_TOKENS,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )["dense_vecs"]
    elapsed = time.time() - t0
    tps = len(texts) / elapsed
    print(f"  done: {len(texts)} docs in {elapsed:.1f}s = {tps:.1f} docs/sec", flush=True)
    print(f"  extrapolated full-corpus (354K): {354000/tps/3600:.1f}h", flush=True)
    arr = np.array(out, dtype=np.float32)
    # normalize (BGE-M3 already normalizes internally, but ensure)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr = arr / np.maximum(norms, 1e-9)
    return arr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=DATA_DIR_DEFAULT)
    args = parser.parse_args()
    d = args.data_dir

    ensure_packages()

    print(f"Loading haystack from {d}...", flush=True)
    ids, texts_tl, texts_to, labse_lists = load_haystack(d)
    print(f"  {len(ids)} haystack articles", flush=True)

    q_ids, q_texts = load_queries(d)
    print(f"  {len(q_ids)} queries", flush=True)

    # ── BGE-M3 title+lead ────────────────────────────────────────────────────
    emb_tl = embed_bge(texts_tl, "title+lead")
    np.save(os.path.join(d, "bge_ab_emb_titlelead.npy"), emb_tl)
    print(f"  saved bge_ab_emb_titlelead.npy {emb_tl.shape}", flush=True)

    # ── BGE-M3 title-only ────────────────────────────────────────────────────
    emb_to = embed_bge(texts_to, "title-only")
    np.save(os.path.join(d, "bge_ab_emb_titleonly.npy"), emb_to)
    print(f"  saved bge_ab_emb_titleonly.npy {emb_to.shape}", flush=True)

    # ── BGE-M3 query embeddings ──────────────────────────────────────────────
    emb_q = embed_bge(q_texts, "queries")
    np.save(os.path.join(d, "bge_ab_emb_queries.npy"), emb_q)
    print(f"  saved bge_ab_emb_queries.npy {emb_q.shape}", flush=True)

    # ── LaBSE embeddings from JSON (already normalised by LaBSE pipeline) ───
    print("  extracting LaBSE embeddings from haystack...", flush=True)
    emb_labse = np.array(labse_lists, dtype=np.float32)
    norms = np.linalg.norm(emb_labse, axis=1, keepdims=True)
    emb_labse = emb_labse / np.maximum(norms, 1e-9)
    np.save(os.path.join(d, "bge_ab_emb_labse.npy"), emb_labse)
    print(f"  saved bge_ab_emb_labse.npy {emb_labse.shape}", flush=True)

    # ── ID order manifest ────────────────────────────────────────────────────
    with open(os.path.join(d, "bge_ab_id_order.json"), "w") as f:
        json.dump(ids, f)
    print(f"  saved bge_ab_id_order.json ({len(ids)} IDs)", flush=True)

    print("\n=== Step 2 complete. Copy all bge_ab_* files to the eval machine. ===")


if __name__ == "__main__":
    main()
