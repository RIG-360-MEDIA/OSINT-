"""Unit tests for the agent: SourceBook (pure) + the loop (mocked LLM + tools)."""
from __future__ import annotations

import json

import pytest

from app.agent import loop as loop_mod
from app.agent.tools import AgentContext, SourceBook
from app.schemas import RetrievedDoc


def _doc(i):
    return RetrievedDoc(id=str(i), title=f"t{i}", snippet="s", url=None, published_at=None,
                        source_id="x", language="en", score=0.0, vec_rank=None, lex_rank=None)


def test_sourcebook_dedup_and_numbering():
    sb = SourceBook()
    assert sb.add(_doc(1)) == 1
    assert sb.add(_doc(2)) == 2
    assert sb.add(_doc(1)) == 1  # same id → same number, not re-added
    assert [d.id for d in sb.docs] == ["1", "2"]


# ---- fakes for the loop ----
class _Fn:
    def __init__(self, name, args):
        self.name = name
        self.arguments = args


class _TC:
    def __init__(self, cid, name, args):
        self.id = cid
        self.function = _Fn(name, args)


class _Msg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeLLM:
    def __init__(self, script):
        self.script = script
        self.i = 0

    def chat(self, messages, tools=None):
        m = self.script[self.i]
        self.i += 1
        return m

    def complete(self, system, user):
        return ""


@pytest.mark.asyncio
async def test_agent_runs_tool_then_answers(monkeypatch):
    async def fake_exec(ctx, name, args):
        ctx.sources.add(_doc(1))
        return "[S1] some evidence"

    monkeypatch.setattr(loop_mod, "execute_tool", fake_exec)
    llm = _FakeLLM([
        _Msg(tool_calls=[_TC("c1", "corpus_search", json.dumps({"query": "x"}))]),
        _Msg(content="The finding is grounded [S1]."),
    ])
    ctx = AgentContext(conn=None, settings=None, embedder=None)
    res = await loop_mod.run_agent(ctx, llm, [], "question", max_steps=5)
    assert res["steps"] == 1
    assert res["trace"][0]["tool"] == "corpus_search"
    assert res["faithful"] is True
    assert len(res["sources"]) == 1 and "[S1]" in res["answer"]


@pytest.mark.asyncio
async def test_agent_forces_final_on_max_steps(monkeypatch):
    async def fake_exec(ctx, name, args):
        return "obs"

    monkeypatch.setattr(loop_mod, "execute_tool", fake_exec)
    tool_msg = _Msg(tool_calls=[_TC("c", "corpus_search", "{}")])
    final = _Msg(content="Forced final answer.")
    llm = _FakeLLM([tool_msg, tool_msg, final])  # 2 tool turns then a forced final
    ctx = AgentContext(conn=None, settings=None, embedder=None)
    res = await loop_mod.run_agent(ctx, llm, [], "q", max_steps=2)
    assert res["steps"] == 2
    assert res["answer"] == "Forced final answer."
    # no sources + no [S#] → not faithful
    assert res["faithful"] is False


@pytest.mark.asyncio
async def test_agent_strips_invalid_citations(monkeypatch):
    async def fake_exec(ctx, name, args):
        ctx.sources.add(_doc(1))  # only S1 exists
        return "[S1]"

    monkeypatch.setattr(loop_mod, "execute_tool", fake_exec)
    llm = _FakeLLM([
        _Msg(tool_calls=[_TC("c1", "corpus_search", "{}")]),
        _Msg(content="Real [S1] but invented [S9]."),
    ])
    ctx = AgentContext(conn=None, settings=None, embedder=None)
    res = await loop_mod.run_agent(ctx, llm, [], "q", max_steps=5)
    assert "[S9]" not in res["answer"]  # out-of-range citation stripped
    assert "[S1]" in res["answer"]
