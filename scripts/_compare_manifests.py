"""Diff local vs Hetzner content manifests; write full report + print summary."""
from __future__ import annotations
from collections import defaultdict


def load(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if "\t" not in line:
                continue
            p, h = line.split("\t", 1)
            out[p] = h
    return out


local = load("local_manifest.tsv")
hetz = load("hetzner_manifest.tsv")

lset, hset = set(local), set(hetz)
only_local = sorted(lset - hset)
only_hetz = sorted(hset - lset)
both = lset & hset
differ = sorted(p for p in both if local[p] != hetz[p])
same = sorted(p for p in both if local[p] == hetz[p])


def top(p: str) -> str:
    parts = p.split("/")
    if parts[0] in ("backend", "frontend", "products", "scripts", "docs",
                     "infrastructure", "archive"):
        return "/".join(parts[:2]) if len(parts) > 1 else parts[0]
    return parts[0]


def bucket(paths: list[str]) -> dict[str, int]:
    d: dict[str, int] = defaultdict(int)
    for p in paths:
        d[top(p)] += 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


report = "manifest_diff_report.txt"
with open(report, "w", encoding="utf-8") as fh:
    def w(s: str = "") -> None:
        fh.write(s + "\n")

    w("=" * 70)
    w("LOCAL (feat/newspaper-hybrid-extraction @145dbd9) vs HETZNER /root/rig")
    w("=" * 70)
    w(f"local files     : {len(local)}")
    w(f"hetzner files   : {len(hetz)}")
    w(f"identical       : {len(same)}")
    w(f"DIFFER (content): {len(differ)}")
    w(f"only on LOCAL   : {len(only_local)}")
    w(f"only on HETZNER : {len(only_hetz)}")
    w("")

    for title, paths in (
        ("CONTENT DIFFERS (exists both sides, different content)", differ),
        ("ONLY ON LOCAL (Hetzner is missing these)", only_local),
        ("ONLY ON HETZNER (local/my branch is missing these)", only_hetz),
    ):
        w("#" * 70)
        w(f"# {title} — {len(paths)}")
        w("#" * 70)
        for area, n in bucket(paths).items():
            w(f"   [{n:>4}]  {area}/")
        w("")
        for p in paths:
            w(p)
        w("")

# Console summary
print("=== SUMMARY ===")
print(f"identical={len(same)} differ={len(differ)} "
      f"only_local={len(only_local)} only_hetzner={len(only_hetz)}")
print("\n-- DIFFER by area --")
for a, n in list(bucket(differ).items())[:15]:
    print(f"  {n:>4}  {a}")
print("\n-- ONLY ON LOCAL by area --")
for a, n in list(bucket(only_local).items())[:15]:
    print(f"  {n:>4}  {a}")
print("\n-- ONLY ON HETZNER by area --")
for a, n in list(bucket(only_hetz).items())[:15]:
    print(f"  {n:>4}  {a}")
print(f"\nFull report: {report}")
