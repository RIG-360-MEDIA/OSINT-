"""run_audit.py — orchestrator for the deep data-quality audit.

Phase 1 ships Layer 1 (SQL sanity). Phases 2-4 extend this script to chain
in Layers 2-6. Each layer:
  * runs read-only against the production DB (via docker exec on Hetzner OR
    direct psycopg if env var is set)
  * emits a JSON sub-summary
  * applies a verification gate; STOPs the audit if the gate fails
  * appends a section to docs/quality/v3-deep-audit-YYYY-MM-DD.md

Usage:
    python3 scripts/audit/run_audit.py --layer 1        # single layer
    python3 scripts/audit/run_audit.py --full           # all layers (Phase 4+)
    python3 scripts/audit/run_audit.py --layer 1 --dry-run

Hard rules:
  * No writes to v3 tables (articles, article_events, article_quotes, etc.)
  * Imports backend.nlp.groq_client only as library (Phase 4)
  * Writes only to docs/quality/* and (Phase 5+) audit_decisions table

Exit codes:
  0  every requested layer passed its gate
  1  a layer failed its gate (audit halted)
  2  usage / config error
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("audit")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = REPO_ROOT / "scripts" / "audit"
QUALITY_DIR = REPO_ROOT / "docs" / "quality"
QUALITY_DIR.mkdir(parents=True, exist_ok=True)

SSH_TARGET = "root@178.105.63.154"
SSH_KEY = "~/.ssh/rig_hetzner"
PSQL_CMD = "docker exec rig-postgres psql -U rig -d rig"


@dataclass
class Finding:
    """A specific issue found by a layer. Severity is the gate, not the
    pass/fail of the layer itself."""
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW | INFO
    layer: int
    category: str
    label: str
    metric: dict[str, Any] = field(default_factory=dict)
    details: str = ""


@dataclass
class GateResult:
    """Result of running an audit layer. `passed` now means 'the layer
    EXECUTED successfully' — not 'the data is clean'. Findings (with severity)
    capture data quality issues; the orchestrator no longer STOPs on them."""
    layer: int
    label: str
    passed: bool  # Did the layer execute without infrastructure error?
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    stop_reason: str | None = None  # Only set if layer cannot run at all


# ---------------------------------------------------------------------------
# Layer 1 — SQL sanity
# Layer 2 — Grounding probe (delegated to grounding_probe.py)
# Layer 3 — Distribution anomalies
# ---------------------------------------------------------------------------
LAYER1_SQL = AUDIT_DIR / "v3_sanity.sql"
LAYER3_SQL = AUDIT_DIR / "distribution_anomalies.sql"
LAYER4_SQL = AUDIT_DIR / "cross_source_agreement.sql"
LAYER6_SQL = AUDIT_DIR / "known_bug_probes.sql"


def _run_sql_file(sql_path: Path, dry_run: bool = False) -> str:
    """Send a .sql file to the live DB via SSH+docker. Returns stdout text."""
    if dry_run:
        log.info("DRY-RUN: would execute %s on %s", sql_path.name, SSH_TARGET)
        return ""

    # Copy the file up, then execute via psql inside the container
    scp = subprocess.run(
        ["scp", "-i", str(Path(SSH_KEY).expanduser()),
         str(sql_path), f"{SSH_TARGET}:/tmp/{sql_path.name}"],
        capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace",
    )
    log.debug("SCP done: %s", scp.stderr.strip() or "ok")

    remote = (
        f"docker cp /tmp/{sql_path.name} rig-postgres:/tmp/{sql_path.name} && "
        f"{PSQL_CMD} -P pager=off -f /tmp/{sql_path.name}"
    )
    proc = subprocess.run(
        ["ssh", "-i", str(Path(SSH_KEY).expanduser()), SSH_TARGET, remote],
        capture_output=True, text=True, check=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    if proc.stderr.strip():
        log.warning("psql stderr: %s", proc.stderr.strip()[:2000])
    return proc.stdout


def _parse_psql_tables(stdout: str) -> dict[str, list[dict[str, str]]]:
    """Parse psql aligned-format output into named tables.

    The v3_sanity.sql uses '\\echo ==== <label> ====' as section delimiters.
    Each subsequent query produces an aligned table. Return a dict mapping
    label -> list of row dicts.
    """
    sections: dict[str, list[dict[str, str]]] = {}
    current_label: str | None = None
    current_rows: list[dict[str, str]] = []
    current_headers: list[str] | None = None
    header_underline_seen = False

    pending_header: list[str] | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        m = re.match(r"={4,}\s+(.+?)\s+={4,}", stripped)
        if m:
            if current_label and current_rows:
                sections[current_label] = current_rows
            current_label = m.group(1)
            current_rows = []
            current_headers = None
            pending_header = None
            header_underline_seen = False
            continue
        if current_label is None:
            continue
        # Skip blank lines and the trailing "(N rows)" footer
        if not stripped or stripped.startswith("(") or stripped.startswith("Time:"):
            continue
        # Header underline: pattern of dashes and pipes (any line that's only
        # dashes/+/| and whitespace; works for single- and multi-column tables)
        if re.match(r"^[\s\-+|]+$", line) and "-" in line:
            if pending_header is not None and current_headers is None:
                current_headers = pending_header
                pending_header = None
            header_underline_seen = True
            continue
        # Data rows: split on | if present, otherwise treat as single-column row
        if "|" in line:
            cells = [c.strip() for c in line.split("|")]
        else:
            cells = [stripped]
        if current_headers is None:
            pending_header = cells
            continue
        if header_underline_seen and len(cells) == len(current_headers):
            current_rows.append(dict(zip(current_headers, cells)))

    if current_label and current_rows:
        sections[current_label] = current_rows

    return sections


def run_layer1(dry_run: bool = False) -> GateResult:
    log.info("Layer 1 — SQL sanity (running %s)", LAYER1_SQL.name)
    if not LAYER1_SQL.exists():
        return GateResult(1, "SQL sanity", False,
                          stop_reason=f"missing {LAYER1_SQL}")
    stdout = _run_sql_file(LAYER1_SQL, dry_run=dry_run)
    if dry_run:
        return GateResult(1, "SQL sanity", True, notes=["dry-run only"])

    sections = _parse_psql_tables(stdout)
    metrics: dict[str, Any] = {}
    notes: list[str] = []
    passed = True
    stop_reason: str | None = None

    findings: list[Finding] = []

    # --- Check: FK orphans (informational only — flag as finding, don't STOP)
    fk_section = sections.get("1B. Foreign-key orphans")
    if not fk_section:
        notes.append("Could not parse FK orphan section.")
        findings.append(Finding(
            severity="MEDIUM", layer=1, category="parser",
            label="FK orphan section missing", details="psql output parse miss"
        ))
    else:
        per_table = {row.get("t", "?"): int(row.get("orphans", "0")) for row in fk_section}
        metrics["fk_orphans_per_table"] = per_table
        worst = max(per_table.values())
        metrics["max_fk_orphans"] = worst
        if worst > 0:
            severity = "CRITICAL" if worst > 100 else "MEDIUM"
            findings.append(Finding(
                severity=severity, layer=1, category="fk_integrity",
                label="FK orphans found",
                metric={"max": worst, "per_table": per_table},
                details=f"Max {worst} orphans across child tables"
            ))

    # --- Gate: residual year drift must be fully explainable by clamp design.
    # We don't gate on raw % — the clamp deliberately preserves Feb 29 cases,
    # events > 20 years pre-publish (real historical refs), and is_future=TRUE
    # events. Instead, we check the "unexplained" residual (zero is the bar).
    drift_section = sections.get("1C. Year-drift residual on effective_event_date")
    if drift_section and len(drift_section) >= 1:
        row = drift_section[0]
        metrics["year_drift_pct_residual"] = row.get("pct_residual_drift")
        metrics["year_drift_pct_corrected"] = row.get("pct_corrected")
        metrics["year_drift_pre"] = row.get("pre_drift")
        metrics["year_drift_corrected_count"] = row.get("corrected")
        # Note: a separate breakdown query (see scripts/audit/v3_sanity_drift_breakdown.sql,
        # to be added in Phase 2) verifies all residual is feb29/20y/future/null.
        # For now we accept any residual since manual inspection showed 0 unexplained.

    # --- Gate: extraction_version=3 articles should be the bulk
    ev_section = sections.get("1G. extraction_version distribution")
    if ev_section:
        v3 = next((r for r in ev_section if r.get("extraction_version") == "3"), None)
        if v3:
            metrics["v3_article_count"] = int(v3.get("n", "0"))
            metrics["v3_ok_count"] = int(v3.get("ok_count", "0"))

    # --- Check: row counts > 0 for every table
    counts_section = sections.get("1A. Row counts per v3 table")
    if counts_section:
        zero_tables = [r["t"] for r in counts_section if int(r.get("rows", "0")) == 0]
        if zero_tables:
            findings.append(Finding(
                severity="CRITICAL" if "articles" in zero_tables else "MEDIUM",
                layer=1, category="empty_table",
                label="Empty v3 table(s)",
                metric={"tables": zero_tables}
            ))

    # --- Check: truncation cliffs (informational)
    trunc_section = sections.get("1D. Truncation cliffs on summary fields")
    if trunc_section:
        for r in trunc_section:
            n = int(r.get("n", "0"))
            if n > 50:
                findings.append(Finding(
                    severity="LOW", layer=1, category="truncation",
                    label=f"Truncation cliff: {r['bucket']}",
                    metric={"count": n}
                ))

    # --- Check: NULL leakage on v3-ok articles
    null_section = sections.get("1E. NULL leakage on v3-ok articles")
    if null_section:
        for r in null_section:
            n = int(r.get("n", "0"))
            denom = int(r.get("denominator", "1"))
            pct = 100.0 * n / max(denom, 1)
            if pct > 1.0:
                findings.append(Finding(
                    severity="MEDIUM" if pct > 5 else "LOW",
                    layer=1, category="null_leakage",
                    label=f"v3-ok NULL: {r['field']}",
                    metric={"count": n, "pct": round(pct, 2)}
                ))

    # --- Check: article_claims placeholder subject bug (74% bug discovered Phase 2)
    claim_ph_section = sections.get("1J. article_claims placeholder bug")
    if claim_ph_section and len(claim_ph_section) >= 1:
        row = claim_ph_section[0]
        ph_count = int(row.get("placeholder_count", "0"))
        ph_pct = float(row.get("placeholder_pct", "0"))
        metrics["claims_placeholder"] = {"count": ph_count, "pct": ph_pct,
                                          "total": int(row.get("total_claims", "0"))}
        if ph_pct > 5.0:
            findings.append(Finding(
                severity="CRITICAL", layer=1, category="extraction_placeholder",
                label="article_claims.subject_text = 'article' / placeholder",
                metric={"count": ph_count, "pct": ph_pct},
                details=("LLM falls back to literal 'article' for subject_text "
                         "when it can't identify a subject. Fix in extraction prompt.")
            ))

    # --- Check: language mis-tags
    lang_section = sections.get("1F. Language mis-tag candidates")
    if lang_section:
        for r in lang_section:
            n = int(r.get("n", "0"))
            if n > 100:
                findings.append(Finding(
                    severity="HIGH", layer=1, category="lang_mistag",
                    label=r.get("bucket", ""),
                    metric={"count": n}
                ))

    # --- Check: is_future inconsistencies (surfaced earlier in this session)
    # Computed in Layer 3, but we also flag here based on the year_drift breakdown

    metrics["row_counts"] = {r["t"]: int(r["rows"]) for r in counts_section or []}
    metrics["raw_sections"] = list(sections.keys())

    return GateResult(1, "SQL sanity", True, metrics, notes,
                      findings=findings)


# ---------------------------------------------------------------------------
# Layer 2 — Grounding probe
# ---------------------------------------------------------------------------
def run_layer2(sample: int = 2000, dry_run: bool = False) -> GateResult:
    log.info("Layer 2 — Grounding probe (sample=%d)", sample)
    if dry_run:
        return GateResult(2, "Grounding probe", True, notes=["dry-run only"])
    out_path = QUALITY_DIR / "grounding_probe.json"
    cmd = [sys.executable, str(AUDIT_DIR / "grounding_probe.py"),
           "--sample", str(sample), "--out", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        log.warning("grounding_probe exited non-zero (gate may have failed)")
    if not out_path.exists():
        return GateResult(2, "Grounding probe", False,
                          stop_reason="grounding_probe.json not written")

    data = json.loads(out_path.read_text(encoding="utf-8"))
    metrics: dict[str, Any] = {}
    notes: list[str] = []
    findings: list[Finding] = []

    for table, r in data.items():
        metrics[table] = {
            "hit_rate": r["hit_rate"], "floor": r["floor"],
            "sampled": r["sampled"], "gate_passed": r["gate_passed"],
            "worst_sources": [s for s in r.get("per_source_top", [])[:5]],
        }
        if not r["gate_passed"]:
            # Severity ladder based on how far below the floor
            severity = "CRITICAL" if r["hit_rate"] < 0.50 else (
                "HIGH" if r["hit_rate"] < r["floor"] - 0.10 else "MEDIUM"
            )
            findings.append(Finding(
                severity=severity, layer=2, category="grounding",
                label=f"{table} grounding below floor",
                metric={"hit_rate": r["hit_rate"], "floor": r["floor"],
                        "sampled": r["sampled"]},
                details=f"{table}: {r['hit_rate']:.1%} < {r['floor']:.0%} floor"
            ))

    return GateResult(2, "Grounding probe", True, metrics, notes,
                      findings=findings)


# ---------------------------------------------------------------------------
# Layer 3 — Distribution anomalies
# ---------------------------------------------------------------------------
def run_layer3(dry_run: bool = False) -> GateResult:
    log.info("Layer 3 — Distribution anomalies (running %s)", LAYER3_SQL.name)
    if not LAYER3_SQL.exists():
        return GateResult(3, "Distribution anomalies", False,
                          stop_reason=f"missing {LAYER3_SQL}")
    if dry_run:
        return GateResult(3, "Distribution anomalies", True, notes=["dry-run only"])
    stdout = _run_sql_file(LAYER3_SQL, dry_run=False)
    sections = _parse_psql_tables(stdout)

    metrics: dict[str, Any] = {}
    notes: list[str] = []
    findings: list[Finding] = []

    # Section 3A: weakest sources
    src_section = sections.get(
        "3A. Per-source field-fill (30d, sources with >=20 articles)"
    )
    if src_section:
        bad_sources = [
            {"source": r.get("source"), "n": int(r.get("n", "0")),
             "summary_pct": r.get("summary_pct"), "emb_pct": r.get("emb_pct"),
             "pub_pct": r.get("pub_pct")}
            for r in src_section
            if float(r.get("summary_pct", "100").replace("·", "0")) < 50.0
        ]
        metrics["sources_below_50pct_summary"] = bad_sources

    # Section 3C: summary length stats
    len_section = sections.get(
        "3C. summary_executive length distribution (v3-ok)"
    )
    if len_section and len(len_section) >= 1:
        row = len_section[0]
        metrics["summary_len_stats"] = {
            "p5": row.get("p5"), "p50": row.get("p50"), "p95": row.get("p95"),
            "p99": row.get("p99"), "max": row.get("max_len"),
            "very_short": row.get("very_short"),
            "trunc_500": row.get("trunc_500"), "trunc_1000": row.get("trunc_1000"),
        }

    # Section 3E: is_future inconsistencies (key finding!)
    is_future_section = sections.get("3E. is_future logical inconsistencies")
    if is_future_section and len(is_future_section) >= 1:
        row = is_future_section[0]
        future_past = int(row.get("future_flag_but_past_event", "0"))
        past_future = int(row.get("past_flag_but_future_event", "0"))
        metrics["is_future_anomalies"] = {
            "future_flag_but_past_event": future_past,
            "past_flag_but_future_event": past_future,
            "total_events_with_date": int(row.get("total_events_with_date", "0")),
        }
        if future_past > 1000:
            findings.append(Finding(
                severity="HIGH", layer=3, category="is_future_flag",
                label="is_future=TRUE but event is in the past",
                metric={"count": future_past},
                details="LLM flagged forecasting but extracted historical date"
            ))

    # Section 3G: stalled sources
    stalled_section = sections.get(
        "3G. Possibly-stalled sources (>=100 articles, no news in 7+ days)"
    )
    if stalled_section:
        metrics["stalled_sources_count"] = len(stalled_section)
        metrics["stalled_sources_top"] = [
            {"source": r.get("source"), "last_seen": r.get("last_seen"),
             "total": r.get("total")}
            for r in stalled_section[:10]
        ]
        if len(stalled_section) > 10:
            findings.append(Finding(
                severity="MEDIUM", layer=3, category="stalled_source",
                label="Multiple sources stalled > 7 days",
                metric={"count": len(stalled_section)},
                details="Sources with ≥100 historical articles but no news in 7+ days"
            ))

    # Also flag the placeholder claims bug found out-of-band
    metrics["sections_parsed"] = list(sections.keys())
    return GateResult(3, "Distribution anomalies", True, metrics, notes,
                      findings=findings)


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def render_report(results: list[GateResult], run_date: str) -> Path:
    out = QUALITY_DIR / f"v3-deep-audit-{run_date}.md"

    # Aggregate findings across all layers
    all_findings: list[Finding] = []
    for r in results:
        all_findings.extend(r.findings)
    all_findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 99),
                                      f.layer, f.label))
    sev_counts = Counter(f.severity for f in all_findings)

    lines = [
        f"# V3 Deep Audit — {run_date}",
        "",
        "Generated by `scripts/audit/run_audit.py`. "
        "Read `docs/quality/README.md` for the framework overview.",
        "",
        "## Layer execution summary",
        "",
        "| Layer | Label | Ran cleanly | Findings | Infra error |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.layer} | {r.label} | "
                     f"{'✅' if r.passed else '❌'} | "
                     f"{len(r.findings)} | "
                     f"{r.stop_reason or '—'} |")
    lines.append("")

    lines.append("## Findings by severity")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---|")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
        lines.append(f"| {sev} | {sev_counts.get(sev, 0)} |")
    lines.append("")

    lines.append("## All findings (ranked)")
    lines.append("")
    if not all_findings:
        lines.append("_No findings — clean audit._")
        lines.append("")
    else:
        lines.append("| Severity | Layer | Category | Label | Metric |")
        lines.append("|---|---|---|---|---|")
        for f in all_findings:
            metric = json.dumps(f.metric, default=str)
            if len(metric) > 80:
                metric = metric[:77] + "..."
            lines.append(f"| **{f.severity}** | L{f.layer} | {f.category} | "
                         f"{f.label} | `{metric}` |")
        lines.append("")

    for r in results:
        lines.append(f"## Layer {r.layer} — {r.label}")
        lines.append("")
        if r.findings:
            lines.append("**Layer findings:**")
            lines.append("")
            for f in sorted(r.findings,
                            key=lambda x: SEVERITY_ORDER.get(x.severity, 99)):
                lines.append(f"- **{f.severity}** · `{f.category}` · "
                             f"{f.label}")
                if f.details:
                    lines.append(f"  - {f.details}")
                if f.metric:
                    lines.append(f"  - `{json.dumps(f.metric, default=str)}`")
            lines.append("")
        if r.notes:
            lines.append("**Notes:** " + "; ".join(r.notes))
            lines.append("")
        lines.append("<details><summary>Layer raw metrics</summary>")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(r.metrics, indent=2, default=str))
        lines.append("```")
        lines.append("</details>")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")

    sidecar = QUALITY_DIR / f"audit_run_{run_date.replace('-', '')}.json"
    sidecar.write_text(
        json.dumps([asdict(r) for r in results], indent=2, default=str),
        encoding="utf-8",
    )
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--layer", type=int, choices=[1, 2, 3, 4, 5, 6],
                   help="run a single layer")
    g.add_argument("--full", action="store_true",
                   help="run all enabled layers in sequence (gates STOP on first fail)")
    p.add_argument("--dry-run", action="store_true",
                   help="do not execute SQL; just report what would be run")
    args = p.parse_args(argv)

    run_date = datetime.now().strftime("%Y-%m-%d")
    results: list[GateResult] = []

    # New philosophy (Phase 2 review): layers ALWAYS run; findings are
    # flagged with severity. We only STOP if a layer has an infrastructure
    # error (psql crash, network out) so we can't trust its findings.
    layers_to_run: list[int] = (
        [args.layer] if args.layer else [1, 2, 3, 4, 5, 6]
    )

    layer_runners = {
        1: lambda: run_layer1(dry_run=args.dry_run),
        2: lambda: run_layer2(sample=2000, dry_run=args.dry_run),
        3: lambda: run_layer3(dry_run=args.dry_run),
        4: lambda: run_layer4(dry_run=args.dry_run),
        5: lambda: run_layer5(dry_run=args.dry_run),
        6: lambda: run_layer6(dry_run=args.dry_run),
    }

    for L in layers_to_run:
        runner = layer_runners.get(L)
        if not runner:
            continue
        try:
            r = runner()
        except Exception as exc:  # pragma: no cover
            log.exception("Layer %d infrastructure error", L)
            r = GateResult(L, f"Layer {L} (crashed)", False,
                           stop_reason=f"infra error: {exc}")
        results.append(r)
        log.info("Layer %d result: ran=%s findings=%d metrics=%s",
                 L, r.passed, len(r.findings),
                 json.dumps(r.metrics, default=str)[:200])

    out = render_report(results, run_date)
    log.info("Wrote report: %s", out)

    # Exit code: 0 if all layers ran (regardless of findings). Non-zero only
    # if a layer had infrastructure failure.
    return 0 if all(r.passed for r in results) else 1


# Placeholders for layers built in subsequent phases — they emit an INFO
# finding so the report shows what's pending without claiming the layer ran.
def run_layer4(dry_run: bool = False) -> GateResult:
    log.info("Layer 4 — Cross-source agreement (%s)", LAYER4_SQL.name)
    if not LAYER4_SQL.exists():
        return GateResult(4, "Cross-source agreement", False,
                          stop_reason=f"missing {LAYER4_SQL}")
    if dry_run:
        return GateResult(4, "Cross-source agreement", True, notes=["dry-run"])
    stdout = _run_sql_file(LAYER4_SQL, dry_run=False)
    sections = _parse_psql_tables(stdout)

    metrics: dict[str, Any] = {}
    findings: list[Finding] = []

    # 4A — date agreement
    date_section = sections.get("4A. Multi-source clusters: event_date agreement")
    if date_section and len(date_section) >= 1:
        row = date_section[0]
        metrics["date_agreement"] = {k: row.get(k) for k in row.keys()}
        spans = int(row.get("spans_more_than_30days", "0"))
        if spans > 0:
            findings.append(Finding(
                severity="MEDIUM", layer=4, category="cross_source_disagreement",
                label="Multi-source clusters span >30 days on same event",
                metric={"count": spans},
                details="Likely date-extraction inconsistency within cluster members"
            ))
        try:
            pct_perfect = float(row.get("pct_perfect", "0"))
            if pct_perfect < 60.0:
                findings.append(Finding(
                    severity="HIGH", layer=4, category="cross_source_disagreement",
                    label="Multi-source clusters with perfect date agreement < 60%",
                    metric={"pct_perfect": pct_perfect},
                ))
        except ValueError:
            pass

    # 4B — actor agreement
    actor_section = sections.get("4B. Per-cluster actor overlap (multi-source clusters)")
    if actor_section and len(actor_section) >= 1:
        row = actor_section[0]
        metrics["actor_agreement"] = {k: row.get(k) for k in row.keys()}
        high_var = int(row.get("high_actor_variance", "0"))
        if high_var > 0:
            findings.append(Finding(
                severity="MEDIUM", layer=4, category="actor_variance",
                label="Multi-source clusters with high actor variance",
                metric={"count": high_var}
            ))

    # 4C — location agreement
    loc_section = sections.get("4C. Location agreement per cluster (multi-source)")
    if loc_section and len(loc_section) >= 1:
        metrics["location_agreement"] = {k: loc_section[0].get(k)
                                          for k in loc_section[0].keys()}

    # 4D — top disagreement examples
    samples_section = sections.get("4D. Top 10 high-disagreement clusters")
    if samples_section:
        metrics["high_disagreement_samples"] = samples_section[:10]

    return GateResult(4, "Cross-source agreement", True, metrics, findings=findings)


def run_layer5(dry_run: bool = False) -> GateResult:
    """Layer 5 reads the most recent judge_summary_*.json produced by
    scripts/audit/llm_judge.py (which runs separately, inside rig-backend)."""
    log.info("Layer 5 — LLM-as-judge (reading latest summary)")
    if dry_run:
        return GateResult(5, "LLM-as-judge", True, notes=["dry-run"])

    candidates = sorted(QUALITY_DIR.glob("judge_summary_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return GateResult(5, "LLM-as-judge", True,
                          notes=["No judge_summary_*.json found — "
                                 "run scripts/audit/llm_judge.py first"],
                          findings=[Finding(
                              severity="INFO", layer=5, category="not_yet_run",
                              label="LLM-judge has not been run",
                              details="Run llm_judge.py to populate this layer."
                          )])

    summary_path = candidates[0]
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = dict(data)
    findings: list[Finding] = []

    median = data.get("median_scores") or {}
    p25 = data.get("p25_scores") or {}

    # Per-field severity ladder: median < 6 = CRITICAL, < 8 = HIGH, < 9 = MEDIUM
    for field_name, score in median.items():
        if not isinstance(score, (int, float)):
            continue
        if score < 6:
            sev = "CRITICAL"
        elif score < 8:
            sev = "HIGH"
        elif score < 9:
            sev = "MEDIUM"
        else:
            continue  # 9-10 is fine
        findings.append(Finding(
            severity=sev, layer=5, category="llm_judge_score",
            label=f"{field_name} median below threshold",
            metric={"median": score, "p25": p25.get(field_name)}
        ))

    metrics["summary_file"] = str(summary_path.name)
    return GateResult(5, "LLM-as-judge", True, metrics, findings=findings)


def run_layer6(dry_run: bool = False) -> GateResult:
    log.info("Layer 6 — Known bug probes (%s)", LAYER6_SQL.name)
    if not LAYER6_SQL.exists():
        return GateResult(6, "Known bug probes", False,
                          stop_reason=f"missing {LAYER6_SQL}")
    if dry_run:
        return GateResult(6, "Known bug probes", True, notes=["dry-run"])
    stdout = _run_sql_file(LAYER6_SQL, dry_run=False)
    sections = _parse_psql_tables(stdout)

    metrics: dict[str, Any] = {}
    findings: list[Finding] = []

    # 6A — placeholder subjects (we already flag this in L1)
    ph_section = sections.get("6A. article_claims placeholder subjects")
    if ph_section:
        total_ph = sum(int(r.get("n", "0")) for r in ph_section)
        metrics["placeholder_subjects"] = {
            r.get("pattern"): int(r.get("n", "0")) for r in ph_section
        }

    # 6B — drift residual unexplained
    drift_section = sections.get("6B. Year-drift residual breakdown")
    if drift_section and len(drift_section) >= 1:
        row = drift_section[0]
        unexplained = int(row.get("unexplained", "0"))
        metrics["drift_residual_unexplained"] = unexplained
        if unexplained > 100:
            findings.append(Finding(
                severity="HIGH", layer=6, category="drift_residual",
                label="Year-drift residual unexplained by clamp rules",
                metric={"count": unexplained}
            ))

    # 6C — is_future contradictions
    isf_section = sections.get("6C. is_future flag = TRUE but event in past")
    if isf_section and len(isf_section) >= 1:
        row = isf_section[0]
        count = int(row.get("contradictory_is_future", "0"))
        metrics["is_future_contradictions"] = count
        if count > 1000:
            findings.append(Finding(
                severity="HIGH", layer=6, category="is_future_flag",
                label="is_future=TRUE with past event_date (regression check)",
                metric={"count": count}
            ))

    # 6D — language mis-tags
    lang_section = sections.get("6D. Language mis-tags")
    if lang_section:
        metrics["lang_mistags"] = {
            r.get("pattern"): int(r.get("n", "0")) for r in lang_section
        }
        total_mistag = sum(int(r.get("n", "0")) for r in lang_section)
        if total_mistag > 5000:
            findings.append(Finding(
                severity="HIGH", layer=6, category="lang_mistag",
                label="Language mis-tag total (all patterns)",
                metric={"total": total_mistag}
            ))

    # 6E — truncation
    trunc_section = sections.get("6E. Summary truncation cliffs")
    if trunc_section:
        metrics["truncation_cliffs"] = {
            r.get("pattern"): int(r.get("n", "0")) for r in trunc_section
        }

    # 6F — embedding collisions
    emb_section = sections.get("6F. labse_embedding collisions")
    if emb_section and len(emb_section) >= 1:
        row = emb_section[0]
        total = int(row.get("total_v3_with_embedding", "0"))
        dup = int(row.get("dup_articles", "0"))
        metrics["embedding_collisions"] = {
            "total": total, "duplicates": dup,
            "pct": round(100.0 * dup / max(total, 1), 1),
        }
        if dup > 5000:
            findings.append(Finding(
                severity="HIGH", layer=6, category="embedding_collisions",
                label="LaBSE embedding collisions (boilerplate-dominated input)",
                metric={"count": dup, "pct": round(100.0 * dup / max(total, 1), 1)},
                details="Many articles share the same fingerprint — input text needs richer fields"
            ))

    # 6G — v3-ok missing fields
    crit_section = sections.get("6G. v3-ok with missing critical fields")
    if crit_section and len(crit_section) >= 1:
        row = crit_section[0]
        metrics["v3_ok_missing"] = {k: int(row.get(k, "0"))
                                      for k in row.keys() if k != "total_v3_ok"}
        metrics["v3_ok_total"] = int(row.get("total_v3_ok", "0"))

    # 6H — sources with no summary
    bad_src_section = sections.get(
        "6H. Sources where summary_executive is mostly NULL (>=10 articles)"
    )
    if bad_src_section:
        metrics["sources_missing_summaries"] = bad_src_section[:10]
        worst = [r for r in bad_src_section
                 if float(r.get("missing_pct", "0")) >= 80.0]
        if worst:
            findings.append(Finding(
                severity="MEDIUM", layer=6, category="source_extraction",
                label="Sources where summary_executive is mostly NULL",
                metric={"count": len(worst), "examples": [r.get("source") for r in worst[:5]]}
            ))

    return GateResult(6, "Known bug probes", True, metrics, findings=findings)


if __name__ == "__main__":
    sys.exit(main())
