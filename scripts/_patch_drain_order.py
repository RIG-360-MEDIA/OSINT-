"""Patch run_corpus_pass.py: add DRAIN_OLDEST_FIRST env switch for the claim order.

Default behaviour (DESC, newest-first) is unchanged so the Celery beat task and
existing callers are unaffected. Setting DRAIN_OLDEST_FIRST=1 in a process's env
flips the claim to oldest-first, letting a dedicated local-only drainer chew the
old backlog while the cloud beat task keeps handling fresh inflow.
"""
from __future__ import annotations

PATH = "/root/rig/backend/tasks/substrate/run_corpus_pass.py"

with open(PATH) as f:
    src = f.read()

if "DRAIN_OLDEST_FIRST" in src:
    print("already patched; no change")
    raise SystemExit(0)

# 1) ensure `import os`
if "\nimport os" not in src and not src.startswith("import os"):
    src = src.replace("from __future__ import annotations\n",
                      "from __future__ import annotations\n\nimport os\n", 1)

# 2) module-level order switch, inserted just before `async def run(`
anchor = "async def run(args: argparse.Namespace) -> int:"
switch = (
    '_DRAIN_ORDER = "ASC" if os.getenv("DRAIN_OLDEST_FIRST", "0") == "1" else "DESC"\n'
    "# ^ default DESC (newest-first) keeps beat task + CLI callers identical.\n\n\n"
)
assert anchor in src, "run() anchor not found"
src = src.replace(anchor, switch + anchor, 1)

# 3) make the claim query an f-string and parameterise its ORDER BY
old_q = (
    '    fetched_q = text(\n'
    '        """\n'
    '        UPDATE articles\n'
    "           SET substrate_status = 'processing'\n"
    '         WHERE id IN (\n'
    '           SELECT id FROM articles\n'
    '            WHERE substrate_processed_at IS NULL AND url IS NOT NULL\n'
    "              AND (substrate_status IS NULL OR substrate_status = 'pending')\n"
    '            ORDER BY collected_at DESC\n'
    '            LIMIT :batch\n'
    '            FOR UPDATE SKIP LOCKED\n'
    '         )\n'
    '        RETURNING id::text AS id, title, url\n'
    '        """\n'
    '    )'
)
new_q = (
    '    fetched_q = text(\n'
    '        f"""\n'
    '        UPDATE articles\n'
    "           SET substrate_status = 'processing'\n"
    '         WHERE id IN (\n'
    '           SELECT id FROM articles\n'
    '            WHERE substrate_processed_at IS NULL AND url IS NOT NULL\n'
    "              AND (substrate_status IS NULL OR substrate_status = 'pending')\n"
    '            ORDER BY collected_at {_DRAIN_ORDER}\n'
    '            LIMIT :batch\n'
    '            FOR UPDATE SKIP LOCKED\n'
    '         )\n'
    '        RETURNING id::text AS id, title, url\n'
    '        """\n'
    '    )'
)
assert old_q in src, "claim-query block not found verbatim"
src = src.replace(old_q, new_q, 1)

with open(PATH, "w") as f:
    f.write(src)
print("patched OK")
