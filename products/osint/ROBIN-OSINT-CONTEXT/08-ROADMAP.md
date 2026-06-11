# 08 — Roadmap / What we're considering next

## Near-term, concrete (discussed this session)
- [ ] **Cross-language de-dup for Top Stories** — translate candidate headlines to
      English, then de-dup on the English text, so Telugu+English twins of the same
      event collapse. (Decision pending; small first-load cost.)
- [ ] **Primary-state weighting in relevance** — give the persona's primary state
      a score boost over secondary states (carefully, without destabilizing the
      plan-stable candidate SQL). Would fix the off-state leak at the source.
- [ ] **Event clustering / populate `thread_id`** — the proper foundation for
      robust same-event de-dup (and would help War Room / story surfaces too).
- [ ] **YouTube audio via residential proxy** — only path to transcribe
      caption-less videos. Paid; currently HOLD. Tear down the `rig-ytproxy`
      test container + ufw 4417 rule when decided.
- [ ] **Improve `summary_executive` coverage** upstream (rig-backend NLP).

## Medium-term product
- [ ] Per-card "for you" strategic line (LLM surface `textual.story_for_you`) —
      noted as a planned follow-up in `top_articles.py`.
- [ ] Folder rename `night-desk/` → `robin-osint/` (+ update build/Caddy/deploy
      paths) — deferred; purely cosmetic, higher blast radius.
- [ ] Broaden personas beyond AP/Telangana; harden onboarding wizard.

## Quality / trust (the senior news-AI lens)
- Evaluation harness first: faithfulness scoring, bias/calibration audits,
  per-persona about-precision (the relevance core already has an eval at
  `scripts/eval/relevance_eval.py`).
- Keep anti-fabrication guards on every LLM surface (brief, report, summaries).
- Multilingual is first-class, not a bolt-on.

> When picking up work: confirm with the user which of the "Near-term" items they
> want, since several were left as open decisions.
