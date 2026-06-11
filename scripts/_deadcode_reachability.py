"""Static import-reachability over backend/ from the real runtime entry points.

Seeds = backend.main + backend.celery_app + every module string in celery_app's
`include=[...]` list (Celery imports those at boot). BFS the import graph; any
backend.* module NOT reached is provably unreferenced at load time — deleting it
cannot break worker/API boot. Reachable modules ARE wired in (loaded), even if
not necessarily scheduled/called.

Run inside the container (code at /app):  python /app/scripts/_deadcode_reachability.py
"""
from __future__ import annotations

import ast
import os
import re

ROOT = "/app"
BACKEND = os.path.join(ROOT, "backend")


def module_name(path: str) -> str:
    rel = os.path.relpath(path, ROOT)[:-3]  # strip .py
    return rel.replace(os.sep, ".")


# 1. Index every backend module that exists on disk.
all_mods: set[str] = set()
file_of: dict[str, str] = {}
for dirpath, _dirs, files in os.walk(BACKEND):
    for f in files:
        if f.endswith(".py"):
            p = os.path.join(dirpath, f)
            m = module_name(p)
            if m.endswith(".__init__"):
                m = m[: -len(".__init__")]
            all_mods.add(m)
            file_of[m] = p


def imports_of(path: str, self_mod: str) -> set[str]:
    """All backend.* modules a file imports (absolute + relative resolved)."""
    out: set[str] = set()
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError:
        return out
    pkg = self_mod if os.path.basename(path) == "__init__.py" else self_mod.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("backend"):
                    out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                base = pkg
                for _ in range(node.level - 1):
                    base = base.rsplit(".", 1)[0]
                mod = f"{base}.{node.module}" if node.module else base
            else:
                mod = node.module or ""
            if not mod.startswith("backend"):
                continue
            out.add(mod)
            for a in node.names:  # `from x import y` where y may be a submodule
                out.add(f"{mod}.{a.name}")
    return out


def resolve(target: str) -> set[str]:
    """Map an import target to existing modules (module itself + parent pkg)."""
    hit: set[str] = set()
    if target in all_mods:
        hit.add(target)
    parent = target.rsplit(".", 1)[0]
    if parent in all_mods:
        hit.add(parent)
    return hit


# 2. Seeds: entry points + celery include list.
seeds = {"backend.main", "backend.celery_app"}
cel = open(os.path.join(BACKEND, "celery_app.py"), encoding="utf-8").read()
inc = re.search(r"include=\[(.*?)\]", cel, re.S)
if inc:
    seeds |= {m.group(1) for m in re.finditer(r'"([^"]+)"', inc.group(1))}
seeds = {s for s in seeds if s in all_mods}

# 3. BFS reachability.
reached: set[str] = set()
queue = list(seeds)
while queue:
    cur = queue.pop()
    if cur in reached:
        continue
    reached.add(cur)
    p = file_of.get(cur)
    if not p:
        continue
    for tgt in imports_of(p, cur):
        for r in resolve(tgt):
            if r not in reached:
                queue.append(r)

dead = sorted(all_mods - reached)

# 4. Report — focus on the candidate areas.
def show(title: str, pred) -> None:
    items = [m for m in dead if pred(m)]
    print(f"\n### {title} — {len(items)} DEAD (unreachable)")
    for m in items:
        print(f"   {m}")

print(f"backend modules total : {len(all_mods)}")
print(f"reachable (LIVE)      : {len(reached)}")
print(f"unreachable (DEAD)    : {len(dead)}")
show("routers", lambda m: m.startswith("backend.routers."))
show("tasks.cm", lambda m: m.startswith("backend.tasks.cm"))
show("tasks.coverage", lambda m: m.startswith("backend.tasks.coverage"))
show("tasks.newsroom", lambda m: m.startswith("backend.tasks.newsroom"))
show("tasks.* (other top-level)", lambda m: m.startswith("backend.tasks.")
     and not any(m.startswith(f"backend.tasks.{x}") for x in ("cm", "coverage", "newsroom")))
show("other backend areas", lambda m: not m.startswith("backend.routers.")
     and not m.startswith("backend.tasks."))

# Also flag candidates that ARE reachable (wired in — NOT safe to delete).
cand_re = re.compile(r"(cm_|coverage|newsroom|signals_|thread_|worldmonitor|"
                     r"analyst_|dossier|documents_router|onboarding|debug_router|"
                     r"\.govt|\.social|brief_task|brief_quality|relevance_task|backfill_task)")
wired = sorted(m for m in reached if cand_re.search(m)
               and (m.startswith("backend.routers.") or m.startswith("backend.tasks.")))
print(f"\n### CANDIDATES THAT ARE WIRED IN (reachable — deleting breaks boot) — {len(wired)}")
for m in wired:
    print(f"   {m}")
