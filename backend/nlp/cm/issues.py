"""
Issue clustering for CM Page.

Pulls recent articles + social posts, embeds title || head via the existing
LaBSE pipeline, clusters them, then asks Groq to produce a 3-6 word neutral
noun-phrase label per cluster. Existing cm_issues rows are matched by
centroid cosine ≥ MERGE_THRESHOLD so issues persist across runs.

Clustering:
  1. Try HDBSCAN if available — best for variable-density political stories.
  2. Fall back to sklearn AgglomerativeClustering with cosine + complete linkage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from backend.nlp.groq_client import GroqCallFailed, GroqQuotaExhausted, generate

logger = logging.getLogger(__name__)

MIN_CLUSTER_SIZE = 5
COSINE_DISTANCE_THRESHOLD = 0.32
MERGE_THRESHOLD = 0.78
LABEL_MODEL = "llama-3.3-70b-versatile"

_LABEL_SYSTEM = (
    "You name a single Indian state-politics flashpoint cluster.\n"
    "Given 5 representative news headlines, return ONE neutral noun-phrase\n"
    "label of 3-6 words. No party names. No adjectives like 'controversial'.\n"
    "Output ONLY the label, no quotes, no punctuation, no preamble."
)


@dataclass
class IssueCluster:
    label: str
    slug: str
    centroid: np.ndarray
    member_indices: list[int] = field(default_factory=list)


def _slugify(label: str) -> str:
    out = []
    for ch in label.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    return "-".join(filter(None, "".join(out).split("-")))[:80]


def _cluster_embeddings(emb: np.ndarray) -> np.ndarray:
    """Returns a label vector of length len(emb). -1 means noise / singleton."""
    if len(emb) < MIN_CLUSTER_SIZE:
        return np.full(len(emb), -1, dtype=int)

    try:
        import hdbscan  # type: ignore[import-not-found]

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=MIN_CLUSTER_SIZE,
            min_samples=2,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        norm = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
        return clusterer.fit_predict(norm)
    except ImportError:
        pass

    try:
        from sklearn.cluster import AgglomerativeClustering

        norm = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
        clusterer = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=COSINE_DISTANCE_THRESHOLD,
            metric="cosine",
            linkage="average",
        )
        labels = clusterer.fit_predict(norm)
        sizes: dict[int, int] = {}
        for label in labels:
            sizes[int(label)] = sizes.get(int(label), 0) + 1
        return np.array(
            [int(label) if sizes[int(label)] >= MIN_CLUSTER_SIZE else -1 for label in labels],
            dtype=int,
        )
    except ImportError:
        logger.warning("Neither hdbscan nor sklearn is installed; clustering disabled")
        return np.full(len(emb), -1, dtype=int)


async def _label_cluster(headlines: list[str]) -> str:
    sample = "\n".join(f"- {h.strip()[:160]}" for h in headlines[:5] if h)
    if not sample:
        return ""
    try:
        reply = await generate(
            system=_LABEL_SYSTEM,
            user=sample,
            task_type="classification",
            model=LABEL_MODEL,
        )
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.info("issue label generate failed (%s)", exc)
        return ""
    if not isinstance(reply, str):
        return ""
    label = reply.strip().splitlines()[0].strip(' "\'')
    return label[:80]


def _centroids(emb: np.ndarray, labels: np.ndarray) -> dict[int, np.ndarray]:
    out: dict[int, np.ndarray] = {}
    for label in set(int(l) for l in labels if l >= 0):
        mask = labels == label
        c = emb[mask].mean(axis=0)
        c = c / (np.linalg.norm(c) + 1e-9)
        out[label] = c
    return out


async def cluster_items(
    *,
    items: list[dict],
    embeddings: np.ndarray,
) -> list[IssueCluster]:
    """items: [{'id': int, 'kind': str, 'title': str, 'lead': str}].
    embeddings: shape (n, dim) LaBSE vectors.
    Returns one IssueCluster per produced cluster, with centroid normalised.
    """
    if len(items) != len(embeddings):
        raise ValueError("items and embeddings must align")
    if len(items) < MIN_CLUSTER_SIZE:
        return []

    norm = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9)
    cluster_labels = _cluster_embeddings(norm)
    centroids = _centroids(norm, cluster_labels)

    out: list[IssueCluster] = []
    for label_id, centroid in centroids.items():
        member_indices = [i for i, l in enumerate(cluster_labels) if int(l) == label_id]
        if len(member_indices) < MIN_CLUSTER_SIZE:
            continue
        headlines = [items[i].get("title", "") for i in member_indices[:8]]
        name = await _label_cluster(headlines)
        if not name:
            continue
        out.append(
            IssueCluster(
                label=name,
                slug=_slugify(name) or f"issue-{label_id}",
                centroid=centroid,
                member_indices=member_indices,
            )
        )
    return out


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a, b))


def find_existing_match(
    new_centroid: np.ndarray,
    candidates: list[tuple[int, np.ndarray]],
    threshold: float = MERGE_THRESHOLD,
) -> int | None:
    """Return the existing issue id whose centroid is closest above
    threshold, else None. candidates: [(issue_id, centroid_vec)]."""
    best_id: int | None = None
    best_score = threshold
    for issue_id, c in candidates:
        s = cosine(new_centroid, c)
        if s >= best_score:
            best_score = s
            best_id = issue_id
    return best_id
