"""Faithfulness gate: generate cited answers over the ground-truth queries, then
score each with an independent LLM judge (different model than the generator).

Reports mean faithfulness, refusal rate, and judge coverage. This is the check
the cite-ID guardrail can't do: does the cited source actually back the claim?

Run (needs tunnel + LaBSE + Groq keys):
    .venv/Scripts/python eval/run_faithfulness.py eval/ground_truth.jsonl
Optional: set ASKRIG_JUDGE_MODEL to pick the judge (default openai/gpt-oss-120b).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer import answer_question  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.embedding import LabseEmbedder  # noqa: E402
from app.llm import get_llm, make_provider  # noqa: E402
from app.retrieval import retrieve_and_curate  # noqa: E402
from eval.faithfulness import score_faithfulness  # noqa: E402


async def main(path: str, limit: int | None = None) -> None:
    settings = load_settings()
    embedder = LabseEmbedder(settings.embed_model)
    generator = get_llm(settings)
    judge_model = os.environ.get("ASKRIG_JUDGE_MODEL", "openai/gpt-oss-120b")
    judge = make_provider(settings, model=judge_model)

    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if limit:
        rows = rows[:limit]

    scores: list[float] = []
    refusals = 0
    parse_fail = 0
    judge_errors = 0
    gen_errors = 0
    total_claims = 0

    print(f"queries={len(rows)}  generator={settings.llm_model}  judge={judge_model}\n")
    async with connect(settings) as conn:
        for i, row in enumerate(rows, start=1):
            qvec = embedder.embed(row["query"])
            docs = await retrieve_and_curate(
                conn, settings, row["query"], qvec, None, rerank_enabled=False
            )
            try:
                result = answer_question(generator, row["query"], docs)
            except Exception as exc:  # noqa: BLE001 - generator exhaustion shouldn't kill the run
                gen_errors += 1
                print(f"  [{i:2}] generator error: {str(exc)[:80]}")
                continue
            try:
                fr = score_faithfulness(judge, result.answer, docs)
            except Exception as exc:  # noqa: BLE001 - judge failure shouldn't kill the run
                judge_errors += 1
                print(f"  [{i:2}] judge error: {str(exc)[:80]}")
                continue
            if not fr.parsed:
                parse_fail += 1
            if fr.n_claims == 0 and "enough" in (result.answer or "").lower():
                refusals += 1
            scores.append(fr.score)
            total_claims += fr.n_claims
            flag = "" if fr.score == 1.0 else "  <-- unsupported claim(s)"
            print(f"  [{i:2}] faith={fr.score:.2f} ({fr.n_supported}/{fr.n_claims} claims){flag}")

    n = max(1, len(scores))
    print(
        f"\nMEAN FAITHFULNESS = {sum(scores)/n:.3f}  over {len(scores)} queries"
        f"\n  refusals={refusals}  judge_parse_fail={parse_fail}  judge_errors={judge_errors}"
        f"  gen_errors={gen_errors}  avg_claims/answer={total_claims/n:.1f}"
    )
    print(
        "\nnote: refusals score 1.0 (faithful by construction). A low score here with "
        "high cite-resolution means the model is citing real docs that don't back the claim."
    )


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "eval/ground_truth.example.jsonl"
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    asyncio.run(main(arg, lim))
