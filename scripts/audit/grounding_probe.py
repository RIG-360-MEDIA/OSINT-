"""grounding_probe.py — Layer 2 of the deep data quality audit.

For each LLM-extracted child-table field, check whether its value actually
appears in the source article's body text. Fields the LLM hallucinated will
have low grounding rates.

Algorithm:
  1. Random-sample N rows from each child table (default 2000), joined to
     articles for body text.
  2. For each row, fuzzy-check whether the extracted value substring-matches
     (after normalization) the article's body.
  3. Emit per-field hit-rate + per-source breakdown.
  4. Apply gate: each LLM-derived table must hit a minimum grounding %.

Output: JSON file + section appended to the audit markdown report.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("grounding")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUALITY_DIR = REPO_ROOT / "docs" / "quality"
SSH_TARGET = "root@178.105.63.154"
SSH_KEY = "~/.ssh/rig_hetzner"

# Per-table check spec: (sql, needle_column, body_column_priority, ground_floor)
# The body comes from a combined column (we coalesce lead_translated, scraped, title)
TABLE_SPECS: dict[str, dict[str, Any]] = {
    "article_quotes": {
        "needle_col": "quote_text",
        "extra_col": "speaker_name",
        "floor": 0.70,  # quotes should appear nearly verbatim; 70% baseline
        "match_mode": "quote",
    },
    "article_claims": {
        "needle_col": "subject_text",
        "extra_col": "claim_text",
        "floor": 0.60,  # claims are paraphrased; subject_text should appear
        "match_mode": "phrase",
    },
    "article_numbers": {
        "needle_col": "value",
        "extra_col": "unit",
        "floor": 0.50,
        "match_mode": "number",
    },
    "article_stances": {
        "needle_col": "actor",
        "extra_col": None,
        "floor": 0.70,  # actor names should appear in body
        "match_mode": "phrase",
    },
    "article_locations": {
        "needle_col": "location_text",
        "extra_col": None,
        "floor": 0.70,
        "match_mode": "phrase",
    },
    "article_events": {
        "needle_col": "actors",  # text[] — check at least one actor appears
        "extra_col": "event_description",
        "floor": 0.70,
        "match_mode": "actors_array",
    },
}


def _normalize(text: str | None) -> str:
    """Lowercase + remove diacritics + collapse whitespace."""
    if not text:
        return ""
    # Lowercase
    s = text.lower()
    # Strip diacritics
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_body(row: dict[str, Any]) -> str:
    """Concatenate available body fields with separators."""
    parts = []
    for k in ("title", "primary_subject", "summary_executive",
              "lead_text_translated", "lead_text_original", "full_text_scraped"):
        v = row.get(k)
        if v:
            parts.append(v)
    return _normalize(" | ".join(parts))


def _match_quote(needle: str, body: str) -> bool:
    """Quote grounding: first ~40 normalized chars should appear in body."""
    n = _normalize(needle)
    if len(n) < 8:
        return False
    if len(n) <= 40:
        return n in body
    head = n[:40]
    return head in body


def _match_phrase(needle: str, body: str) -> bool:
    """Phrase grounding: substring after normalization, OR ≥50% token overlap
    if the phrase is long enough to have tokens."""
    n = _normalize(needle)
    if not n or len(n) < 2:
        return False
    if n in body:
        return True
    tokens = [t for t in n.split() if len(t) > 2]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in body)
    return hits / len(tokens) >= 0.5


def _match_number(value: str | None, body: str, unit: str | None = None) -> bool:
    """Number grounding: convert to several display variants and substring-match."""
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    body_n = _normalize(body)
    # Try several variants
    variants = {s, s.replace(",", ""), s.replace(",", " ")}
    # Numeric? add Indian-number formatting (lakh/crore)
    try:
        v = float(s)
        variants.add(f"{int(v)}")
        variants.add(f"{int(v):,}")
        if v >= 100000:
            variants.add(f"{v/100000:.1f} lakh")
            variants.add(f"{int(v/100000)} lakh")
            variants.add(f"{int(v/100000)} lakhs")
        if v >= 10000000:
            variants.add(f"{v/10000000:.1f} crore")
            variants.add(f"{int(v/10000000)} crore")
    except (TypeError, ValueError):
        pass
    for var in variants:
        nvar = _normalize(var)
        if nvar and nvar in body_n:
            return True
    return False


def _match_actors_array(actors: list[str] | None, body: str) -> bool:
    """For article_events.actors[]: at least ONE actor must appear in body."""
    if not actors:
        return False
    for a in actors:
        if _match_phrase(a, body):
            return True
    return False


import csv
import io

# Bump csv field-size limit so very-long article bodies don't trip it.
# Some scraped articles exceed the default 131KB cap; we want them all parsed.
csv.field_size_limit(10 * 1024 * 1024)  # 10MB per field


def _run_psql_real_csv(query: str) -> list[dict[str, str]]:
    """Run a query via psql --csv, return parsed CSV rows as dicts.

    psql's --csv flag emits proper RFC-4180 CSV with double-quote escaping,
    so we can use Python's csv module to parse safely even when fields
    contain commas, pipes, newlines etc.
    """
    cmd = (
        f"docker exec -i rig-postgres psql -U rig -d rig "
        f"--csv -X -c \"{query}\""
    )
    proc = subprocess.run(
        ["ssh", "-i", str(Path(SSH_KEY).expanduser()), SSH_TARGET, cmd],
        capture_output=True, text=True, check=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    if proc.stderr.strip():
        log.warning("psql stderr: %s", proc.stderr.strip()[:1000])
    reader = csv.DictReader(io.StringIO(proc.stdout))
    return [dict(r) for r in reader]


def _parse_pg_array(s: str | None) -> list[str]:
    """Parse postgres text[] CSV-style output like '{Foo,"Bar Baz"}'."""
    if not s or s == "{}":
        return []
    inner = s.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    out: list[str] = []
    buf, in_quote = "", False
    for ch in inner:
        if ch == '"' and (not buf or buf[-1] != "\\"):
            in_quote = not in_quote
            continue
        if ch == "," and not in_quote:
            if buf:
                out.append(buf)
            buf = ""
            continue
        buf += ch
    if buf:
        out.append(buf)
    return [x.replace('\\"', '"').strip() for x in out if x.strip()]


def probe_table(table: str, sample: int, spec: dict[str, Any]) -> dict[str, Any]:
    needle_col = spec["needle_col"]
    extra_col = spec["extra_col"]
    mode = spec["match_mode"]
    floor = spec["floor"]

    # Build SELECT — for actors[] we read the array column directly
    extra_select = f", ae.{extra_col} AS extra" if extra_col else ", NULL AS extra"
    if needle_col == "actors":
        needle_select = "array_to_string(ae.actors, '||') AS needle"
    else:
        needle_select = f"ae.{needle_col}::text AS needle"

    # We only need ~5KB of body for grounding checks — truncate in SQL.
    query = (
        f"SELECT a.id::text AS aid, s.name AS source, a.language_detected AS lang, "
        f"LEFT(a.title, 500) AS title, "
        f"LEFT(a.primary_subject, 500) AS primary_subject, "
        f"LEFT(a.summary_executive, 2000) AS summary_executive, "
        f"LEFT(a.lead_text_translated, 5000) AS lead_text_translated, "
        f"LEFT(a.lead_text_original, 5000) AS lead_text_original, "
        f"LEFT(a.full_text_scraped, 5000) AS full_text_scraped, "
        f"{needle_select}{extra_select} "
        f"FROM {table} ae "
        f"JOIN articles a ON a.id = ae.article_id "
        f"JOIN sources s ON s.id = a.source_id "
        f"WHERE ae.{needle_col} IS NOT NULL "
        f"ORDER BY md5(ae.id::text) LIMIT {int(sample)}"
    )

    log.info("[%s] sampling %d rows...", table, sample)
    rows = _run_psql_real_csv(query)
    log.info("[%s] got %d sampled rows", table, len(rows))

    hits = 0
    misses_examples: list[dict[str, str]] = []
    per_source: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "hits": 0})
    per_lang: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "hits": 0})

    for row in rows:
        body = _build_body(row)
        needle = row.get("needle", "")
        ok = False
        if mode == "quote":
            ok = _match_quote(needle, body)
        elif mode == "phrase":
            ok = _match_phrase(needle, body)
        elif mode == "number":
            ok = _match_number(needle, body, row.get("extra"))
        elif mode == "actors_array":
            actors = _parse_pg_array(needle.replace("||", ","))
            if not actors:
                actors = [x.strip() for x in needle.split("||") if x.strip()]
            ok = _match_actors_array(actors, body)
        if ok:
            hits += 1
        per_source[row["source"]]["n"] += 1
        per_source[row["source"]]["hits"] += int(ok)
        per_lang[row["lang"] or "?"]["n"] += 1
        per_lang[row["lang"] or "?"]["hits"] += int(ok)
        if not ok and len(misses_examples) < 10:
            misses_examples.append({
                "aid": row["aid"], "source": row["source"],
                "needle": (needle or "")[:120],
                "title": (row.get("title") or "")[:80],
            })

    hit_rate = hits / max(len(rows), 1)
    return {
        "table": table,
        "needle_col": needle_col,
        "sampled": len(rows),
        "hits": hits,
        "hit_rate": round(hit_rate, 4),
        "floor": floor,
        "gate_passed": hit_rate >= floor,
        "per_source_top": sorted(
            [{"source": k, "n": v["n"], "hits": v["hits"],
              "hit_rate": round(v["hits"] / max(v["n"], 1), 3)}
             for k, v in per_source.items() if v["n"] >= 5],
            key=lambda x: x["hit_rate"]
        )[:15],
        "per_lang": {k: {"n": v["n"], "hits": v["hits"],
                          "hit_rate": round(v["hits"] / max(v["n"], 1), 3)}
                     for k, v in per_lang.items()},
        "miss_examples": misses_examples,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=2000)
    p.add_argument("--table", help="run only one table")
    p.add_argument("--out", default=str(QUALITY_DIR / "grounding_probe.json"))
    args = p.parse_args(argv)

    tables = [args.table] if args.table else list(TABLE_SPECS.keys())
    results: dict[str, Any] = {}
    overall_pass = True
    for t in tables:
        spec = TABLE_SPECS[t]
        r = probe_table(t, args.sample, spec)
        results[t] = r
        log.info(
            "[%s] hit_rate=%.3f floor=%.2f gate=%s",
            t, r["hit_rate"], r["floor"], "PASS" if r["gate_passed"] else "FAIL"
        )
        if not r["gate_passed"]:
            overall_pass = False

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out_path)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
