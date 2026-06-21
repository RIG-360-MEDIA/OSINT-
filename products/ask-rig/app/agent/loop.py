"""The agent loop: plan → call tools → observe → repeat → final cited answer.

Reuses the cite-ID guardrail (validate over everything the SourceBook gathered)
and the LLM key-pool. Returns a tool trace so the agent can 'show its work'.
"""
from __future__ import annotations

import asyncio
import json

from app.agent.tools import TOOL_SPECS, AgentContext, execute_tool
from app.answer import strip_invalid_markers, to_citations, validate_citations
from app.llm import LLMProvider

AGENT_SYSTEM = (
    "You are RIG, an OSINT research agent over a multilingual Indian news corpus plus the live web. "
    "Plan, then use tools to gather evidence: call resolve_entity BEFORE any entity tool; corpus_search "
    "for background; web_search for fresh/breaking facts; entity_stances / quotes / connect_entities for "
    "analysis. When calling entity tools, pass the EXACT entity_id UUID returned by resolve_entity — never "
    "a citation marker like [S1] or a name. Prefer 1-2 well-chosen tool calls per step. When you have "
    "enough, STOP calling tools and write the final answer using ONLY the gathered [S#] sources, citing "
    "each factual sentence inline like [S1][S3]. Never invent sources or facts; if evidence is thin, say so. "
    "If this is a follow-up in an ongoing conversation, answer the NEW question specifically — run fresh "
    "tool calls for anything not already gathered; do not just repeat a previous answer."
)


def _serialise_tool_calls(tool_calls) -> list[dict]:
    return [
        {"id": tc.id, "type": "function",
         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
        for tc in tool_calls
    ]


async def run_agent(
    ctx: AgentContext,
    llm: LLMProvider,
    history: list[dict],
    user_message: str,
    max_steps: int = 5,
) -> dict:
    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM}, *history,
                            {"role": "user", "content": user_message}]
    trace: list[dict] = []
    answer = ""

    for step in range(max_steps):
        msg = await asyncio.to_thread(llm.chat, messages, TOOL_SPECS)
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            answer = (msg.content or "").strip()
            break
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": _serialise_tool_calls(tool_calls)})
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            observation = await execute_tool(ctx, tc.function.name, args)
            trace.append({"step": step + 1, "tool": tc.function.name, "args": args,
                          "result_preview": observation[:200]})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": observation})
    else:
        # Ran out of steps — force a final answer with no more tools.
        messages.append({"role": "user",
                         "content": "Stop researching. Write the final cited answer now from the sources gathered."})
        final = await asyncio.to_thread(llm.chat, messages, None)
        answer = (final.content or "").strip()

    docs = ctx.sources.docs
    faithful, invalid = validate_citations(answer, len(docs))
    clean = strip_invalid_markers(answer, len(docs)) if invalid else answer
    return {
        "answer": clean,
        "faithful": faithful,
        "citations": to_citations(clean, docs),
        "sources": docs,
        "trace": trace,
        "steps": len(trace),
    }
