# LLM Daily Quota Audit — 2026-05-24

## Question
"Does Cerebras have Qwen?"

## Answer
**Yes.** Cerebras offers `qwen-3-235b-a22b-instruct-2507` — same Qwen3 family as Groq's `qwen/qwen3-32b` and Ollama's `qwen3:30b-a3b`. The code's `_GROQ_TO_CEREBRAS_MODEL` mapping in `backend/nlp/groq_client.py` already routes `qwen/qwen3-32b` Groq calls to it.

## Cerebras Qwen vs alternatives

| Model | Where | Total params | Active per token | Quality vs qwen3-32b |
|---|---|---|---|---|
| `qwen/qwen3-32b` | Groq | 32B | 32B | baseline |
| `qwen-3-235b-a22b-instruct-2507` | **Cerebras** | **235B** | **22B** | match or **exceed** |
| `qwen3:30b-a3b` | Ollama (TRIJYA-7) | 30B | 3B | match (lower active params) |
| `llama3.1-8b` | Cerebras | 8B | 8B | regression (smaller, different family) |

## Today's actual quota state (per-key 1M TPD on each model)

| Provider | Model | Keys | Total TPD | Used | Remaining | % used |
|---|---|---|---|---|---|---|
| Groq | qwen/qwen3-32b | 21 | 10,500,000 | ~9.93M (measured 20) | ~68K (measured) | 99.3% |
| **Cerebras** | **qwen-3-235b** | **27** | **27,000,000** | ~19.7M (measured 20) | **~285K (measured)** | **98.6%** |
| Cerebras | llama3.1-8b | 27 | 27,000,000 | 227K | 26,773K | 0.8% |

## Conclusion that changes my prior advice

**Cerebras Qwen IS exhausted today (98.6%)** — the 26.7M "unused" Cerebras tokens are on `llama3.1-8b`, which is a quality regression for substrate extraction.

There's no safe Cerebras path that gives meaningful capacity today. The midnight-UTC reset will recover ~37.5M combined tokens on the right models.

## Backfill plan unchanged
- **Now → midnight UTC**: Ollama (`qwen3:30b-a3b`) grinding via `LLM_LOCAL_ONLY=1`. Same-family model, JSON shape matches.
- **After 00:00 UTC**: Groq + Cerebras-Qwen reset. Could stop Ollama and let the pool burn through the rest at high speed.
