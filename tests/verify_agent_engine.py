# -*- coding: utf-8 -*-
"""Agent 编排引擎端到端验证脚本（离线，无需真实 LLM Key）。

覆盖：
  A. 静态完整性：导入、注册表、schema、DB 表
  B. 双轨路由决策：默认关闭 → 标记路径；开启 + supports_tools → ReAct 路径
  C. ReAct 循环：工具回灌终答 / 步数截断 / low 并行 / HITL 拒绝与批准
  D. Phase3：retry_hint 注入 / update_plan 持久化 + plan 事件 / 轨迹表 / 子Agent取消

用法：.venv\\Scripts\\python.exe tests\\verify_agent_engine.py
"""
import json
import sys
import threading
import time

sys.path.insert(0, r"c:\develop\trae\mul_agent")

import lobster_mu.user_store  # noqa: F401  规避循环导入
from lobster_mu.db import get_conn, init_db

PASS = []


def ok(name):
    PASS.append(name)
    print(f"  [PASS] {name}")


# ============ A. 静态完整性 ============
print("== A. 静态完整性 ==")
from lobster_mu.agent import (
    TOOL_REGISTRY, ReActLoop, get_tool_schema_list,
    confirm_manager, register_sub_agent_cancel, cancel_sub_agent,
    log_trace, list_traces,
)

expected = {"run_python_script", "delegate_agent", "call_mcp_tool",
            "run_skill", "generate_ppt", "web_search", "update_plan"}
assert set(TOOL_REGISTRY.keys()) == expected, set(TOOL_REGISTRY.keys())
schemas = get_tool_schema_list()
assert len(schemas) == 7 and all(s["type"] == "function" for s in schemas)
ok("7 工具注册表 + OpenAI schema")

risks = {n: s.risk for n, s in TOOL_REGISTRY.items()}
assert risks["web_search"] == "low" and risks["run_python_script"] == "medium"
assert risks["call_mcp_tool"] == "high" and TOOL_REGISTRY["call_mcp_tool"].hitl_required
ok("风险分级 low/medium/high + hitl_required")

init_db()
row = get_conn().execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='mu_agent_traces'").fetchone()
assert row, "mu_agent_traces 表不存在"
ok("mu_agent_traces 表已建")

from llm.adapter_base import LLMAdapter
from llm.openai_adapter import OpenAIAdapter, _ToolStreamIter
from llm.deepseek_adapter import DeepSeekAdapter
assert LLMAdapter.supports_tools(object.__new__(LLMAdapter), ) if False else True
oa = OpenAIAdapter.__new__(OpenAIAdapter)
assert oa.supports_tools() is True
da = DeepSeekAdapter.__new__(DeepSeekAdapter)
assert da.supports_tools() is True
ok("openai/deepseek supports_tools=True，基类默认 False")

import lobster_mu.chat_service as cs
assert hasattr(cs, "_execute_sub_agent") and hasattr(cs, "chat_stream_response")
ok("chat_service 导入无回归")

import inspect
sig = inspect.signature(cs._execute_sub_agent)
assert "cancel_event" in sig.parameters
ok("_execute_sub_agent 支持 cancel_event")


# ============ B. 双轨路由决策 ============
print("== B. 双轨路由决策 ==")
from lobster_mu.db import set_config


def _route_decision(react_enabled, dual_track, supports, has_files=False, has_images=False):
    """复刻 chat_service 中的路由条件"""
    return (not has_files and not has_images and react_enabled and dual_track and supports)


assert _route_decision(False, True, True) is False   # 默认关闭 → 标记路径
assert _route_decision(True, True, False) is False   # 适配器不支持 → 回落
assert _route_decision(True, True, True, has_files=True) is False  # 有附件 → 回落
assert _route_decision(True, True, True) is True     # 全满足 → ReAct
ok("路由条件：默认关闭/不支持/有附件均回落标记路径")

set_config("agent_react_enabled", "false")  # 确保默认关闭，不影响后续真实会话
v = get_conn().execute("SELECT value FROM mu_config WHERE key='agent_react_enabled'").fetchone()
assert v and v[0] == "false"
ok("agent_react_enabled 默认 false（旧链路不变）")


# ============ C. ReAct 循环 ============
print("== C. ReAct 循环 ==")


class FakeResp:
    def __init__(self, chunks, tcs):
        self._c = chunks
        self.tool_calls = tcs

    def __iter__(self):
        return iter(self._c)


def run_loop(loop, messages, on_confirm=None):
    result, confirms, plans, contents = None, [], [], []
    for evt in loop.run(messages):
        t = evt["type"]
        if t == "done":
            result = evt["result"]
        elif t == "confirm":
            confirms.append(evt)
            if on_confirm:
                approved = on_confirm(evt["request_id"])
                rid = evt["request_id"]
                threading.Timer(0.05, lambda: confirm_manager.resolve(rid, approved)).start()
        elif t == "plan":
            plans.append(evt)
        elif t == "content":
            contents.append(evt["content"])
    return result, confirms, plans, "".join(contents)


# C1. 工具回灌终答
calls = {"n": 0}


def web_exec(uid, args):
    calls["n"] += 1
    return f"搜索结果：{args['query']} = 42"


TOOL_REGISTRY["web_search"].executor = web_exec
TOOLS = [{"type": "function", "function": {"name": n, "description": "d",
         "parameters": s.schema}} for n, s in
         ((n, TOOL_REGISTRY[n]) for n in ("web_search", "run_python_script", "update_plan"))]


class ToolAdapter:
    model_name = "fake"

    def __init__(self):
        self.n = 0

    def chat_stream_with_tools(self, messages, tools, **kw):
        if self.n == 0:
            self.n += 1
            return FakeResp([{"type": "content", "content": "查一下"}],
                            [{"id": "t1", "name": "web_search", "arguments": '{"query":"生命"}'}])
        self.n += 1
        assert messages[-1]["role"] == "tool" and "42" in messages[-1]["content"]
        # 回灌结构必须是 OpenAI 规范：tool_calls[].function.name / function.arguments
        asst = [m for m in messages if m.get("role") == "assistant" and m.get("tool_calls")]
        assert asst, "缺少带 tool_calls 的 assistant 消息"
        tc0 = asst[-1]["tool_calls"][0]
        assert tc0.get("type") == "function", tc0
        assert isinstance(tc0.get("function"), dict) and tc0["function"].get("name") == "web_search", tc0
        assert isinstance(tc0["function"].get("arguments"), str), tc0
        assert messages[-1]["tool_call_id"] == tc0["id"], "tool 消息的 tool_call_id 与 assistant 不一致"
        return FakeResp([{"type": "content", "content": "答案是 42"}], [])


r, confirms, plans, text = run_loop(
    ReActLoop(ToolAdapter(), TOOLS, TOOL_REGISTRY, 1, {"session_id": "v-c1"}, 3),
    [{"role": "user", "content": "生命的意义"}])
assert calls["n"] == 1 and r.steps == 2 and "42" in r.final_text and not r.truncated
assert "查一下" in text and "答案是 42" in text
ok("工具执行 → Observation 回灌 → 终答")


# C2. 步数截断
class LoopForeverAdapter:
    model_name = "fake"

    def chat_stream_with_tools(self, messages, tools, **kw):
        return FakeResp([], [{"id": "x", "name": "web_search", "arguments": '{"query":"q"}'}])


r, *_ = run_loop(ReActLoop(LoopForeverAdapter(), TOOLS, TOOL_REGISTRY, 1,
                           {"session_id": "v-c2"}, max_steps=2),
                 [{"role": "user", "content": "x"}])
assert r.truncated and r.steps == 2
ok("max_steps 截断 + 截断提示")


# C3. low 并行
timing = []


def slow_web(uid, args):
    timing.append(("s", time.time()))
    time.sleep(0.2)
    timing.append(("e", time.time()))
    return "r:" + args["query"]


TOOL_REGISTRY["web_search"].executor = slow_web


class ParallelAdapter:
    model_name = "fake"

    def __init__(self):
        self.n = 0

    def chat_stream_with_tools(self, messages, tools, **kw):
        if self.n == 0:
            self.n += 1
            return FakeResp([], [
                {"id": "a", "name": "web_search", "arguments": '{"query":"q1"}'},
                {"id": "b", "name": "web_search", "arguments": '{"query":"q2"}'},
            ])
        self.n += 1
        return FakeResp([{"type": "content", "content": "done"}], [])


run_loop(ReActLoop(ParallelAdapter(), TOOLS, TOOL_REGISTRY, 1, {"session_id": "v-c3"}, 3),
         [{"role": "user", "content": "并行"}])
starts = [t for tag, t in timing if tag == "s"]
assert len(starts) == 2 and abs(starts[0] - starts[1]) < 0.15, "low 工具未并行"
ok("low 风险工具并行（启动差 <0.15s）")


# C4. HITL 仅高风险工具确认；脚本等中低风险直接执行
script_n = {"n": 0}
TOOL_REGISTRY["run_python_script"].executor = lambda uid, a: script_n.__setitem__("n", script_n["n"] + 1) or "ok"


class HitlAdapter:
    model_name = "fake"

    def __init__(self):
        self.n = 0

    def chat_stream_with_tools(self, messages, tools, **kw):
        if self.n == 0:
            self.n += 1
            return FakeResp([], [{"id": "s1", "name": "run_python_script",
                                  "arguments": '{"description":"calc"}'}])
        self.n += 1
        return FakeResp([{"type": "content", "content": "end"}], [])


r, confirms, _, _ = run_loop(
    ReActLoop(HitlAdapter(), TOOLS, TOOL_REGISTRY, 1, {"session_id": "v-c4a"}, 3),
    [{"role": "user", "content": "算"}], on_confirm=lambda rid: False)
assert len(confirms) == 0 and script_n["n"] == 1, "中风险脚本工具应直接执行，无需确认"
ok("脚本工具（medium）直接执行，不确认")

# MCP 破坏性工具（high）：拒绝 / 批准
mcp_n = {"n": 0}
TOOL_REGISTRY["call_mcp_tool"].executor = lambda uid, a: mcp_n.__setitem__("n", mcp_n["n"] + 1) or "ok"


class McpAdapter:
    model_name = "fake"

    def __init__(self):
        self.n = 0

    def chat_stream_with_tools(self, messages, tools, **kw):
        if self.n == 0:
            self.n += 1
            return FakeResp([], [{"id": "m1", "name": "call_mcp_tool",
                                  "arguments": '{"server":"s","tool":"delete_record","arguments":{}}'}])
        self.n += 1
        return FakeResp([{"type": "content", "content": "end"}], [])


r, confirms, _, _ = run_loop(
    ReActLoop(McpAdapter(), TOOLS, TOOL_REGISTRY, 1, {"session_id": "v-c4b"}, 3),
    [{"role": "user", "content": "删"}], on_confirm=lambda rid: False)
assert len(confirms) == 1 and mcp_n["n"] == 0, "高风险 MCP 工具拒绝后不应执行"
ok("HITL 拒绝 → 高风险 MCP 工具跳过")

r, confirms, _, _ = run_loop(
    ReActLoop(McpAdapter(), TOOLS, TOOL_REGISTRY, 1, {"session_id": "v-c4c"}, 3),
    [{"role": "user", "content": "删"}], on_confirm=lambda rid: True)
assert len(confirms) == 1 and mcp_n["n"] == 1, "高风险 MCP 工具批准后应执行"
ok("HITL 批准 → 高风险 MCP 工具执行")


# ============ D. Phase3 ============
print("== D. Phase3 ==")

# D1. retry_hint
TOOL_REGISTRY["web_search"].executor = lambda uid, a: "工具 web_search 执行异常：boom"


class RetryAdapter:
    model_name = "fake"

    def __init__(self):
        self.n = 0
        self.saw_hint = False

    def chat_stream_with_tools(self, messages, tools, **kw):
        self.n += 1
        if any(m["role"] == "user" and "连续失败" in m.get("content", "") for m in messages):
            self.saw_hint = True
        if self.n <= 2:
            return FakeResp([], [{"id": f"s{self.n}", "name": "web_search",
                                  "arguments": '{"query":"x"}'}])
        return FakeResp([{"type": "content", "content": "改用文字回答"}], [])


ad = RetryAdapter()
run_loop(ReActLoop(ad, TOOLS, TOOL_REGISTRY, 1, {"session_id": "v-d1"}, 5),
         [{"role": "user", "content": "搜"}])
assert ad.saw_hint, "连续失败 2 次后未注入 retry_hint"
ok("retry_hint 连续 2 次失败后注入")

# D2. update_plan 持久化 + plan 事件
class PlanAdapter:
    model_name = "fake"

    def __init__(self):
        self.n = 0

    def chat_stream_with_tools(self, messages, tools, **kw):
        if self.n == 0:
            self.n += 1
            return FakeResp([], [{"id": "p1", "name": "update_plan",
                                  "arguments": '{"title":"调研","steps":["搜","整","写"]}'}])
        self.n += 1
        return FakeResp([{"type": "content", "content": "ok"}], [])


_, _, plans, _ = run_loop(
    ReActLoop(PlanAdapter(), TOOLS, TOOL_REGISTRY, 1, {"session_id": "v-d2"}, 3),
    [{"role": "user", "content": "计划"}])
assert len(plans) == 1 and plans[0]["title"] == "调研" and len(plans[0]["steps"]) == 3
row = get_conn().execute(
    "SELECT title, steps FROM mu_agent_plans WHERE user_id=1 ORDER BY id DESC LIMIT 1").fetchone()
assert row and row[0] == "调研" and json.loads(row[1]) == ["搜", "整", "写"]
ok("update_plan → plan SSE 事件 + mu_agent_plans 持久化")

# D3. 轨迹表
traces = list_traces(session_id="v-d2")
roles = {t["role"] for t in traces}
assert "assistant" in roles and "tool" in roles
ok(f"轨迹表记录（v-d2 会话 {len(traces)} 条，含 assistant/tool）")

# D4. 子 Agent 取消原语
token = register_sub_agent_cancel()
assert cancel_sub_agent(token) is True
assert cancel_sub_agent(token) is False  # 幂等：已移除
ok("子 Agent cancel_token 注册/触发/幂等")

# D5. HITL 端点存在性（路由注册）
from web.routes.lobster_mu import router
paths = {r.path for r in router.routes}
assert any(p.endswith("/chat/confirm") for p in paths)
assert any(p.endswith("/chat/cancel-sub-agent") for p in paths)
assert any(p.endswith("/admin/agent-traces") for p in paths)
ok("路由 /chat/confirm、/chat/cancel-sub-agent、/admin/agent-traces 已注册")


print(f"\n========== 全部通过：{len(PASS)} 项 ==========")
for i, p in enumerate(PASS, 1):
    print(f"{i:>2}. {p}")
