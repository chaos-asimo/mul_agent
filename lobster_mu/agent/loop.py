# -*- coding: utf-8 -*-
"""ReAct 最小循环：Thought(Action) → Observation → 循环直到终答或步数上限。

设计要点：
- 调用方传入已配置 tools 的 adapter；每轮调用 chat_stream_with_tools()
- 流式正文直接通过 step_emit 回调转发（虚拟单流）
- 工具执行结果以 role=tool 消息回灌
- 终止：无 tool_calls 或达到 max_steps
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ReActResult:
    final_text: str = ""
    steps: int = 0
    tool_calls_count: int = 0
    truncated: bool = False
    token_stats: Dict[str, int] = field(default_factory=dict)


class ReActLoop:
    # 全局工具执行线程池（low 风险工具并行）；写库工具串行执行避免 SQLite 锁竞争
    _executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="react-tool")
    # 每用户工具占用信号量，避免单用户占满全局池
    _user_tool_sems: Dict[int, threading.BoundedSemaphore] = {}
    _user_tool_lock = threading.Lock()

    def __init__(
        self,
        adapter,
        tools: List[Dict[str, Any]],
        registry: Dict[str, Any],
        user_id: int,
        ctx: Dict[str, Any],
        max_steps: int = 3,
        on_status: Optional[Callable[[str], None]] = None,
        on_confirm: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    ):
        self.adapter = adapter
        self.tools = tools
        self.registry = registry
        self.user_id = user_id
        self.ctx = ctx
        self.max_steps = max_steps
        # on_status 回调：把状态文本写入队列，由 run() 生成器消费并 yield 给前端
        self._status_queue: List[str] = []
        self.on_status = on_status or (lambda s: self._status_queue.append(s))
        # on_confirm(summary, meta) -> bool: 是否批准执行（HITL 安全闸）
        self.on_confirm = on_confirm or (lambda summary, meta: True)
        self.tool_calls_count = 0
        self.token_stats = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @classmethod
    def _user_tool_sem(cls, user_id: int) -> threading.BoundedSemaphore:
        with cls._user_tool_lock:
            sem = cls._user_tool_sems.get(user_id)
            if sem is None:
                sem = threading.BoundedSemaphore(2)
                cls._user_tool_sems[user_id] = sem
            return sem

    def _flush_status(self):
        """把 on_status 回调积压的状态文本作为 status 事件 yield 出去。"""
        while self._status_queue:
            text = self._status_queue.pop(0)
            yield {"type": "status", "text": text}

    @staticmethod
    def _format_confirm_summary(tool_name: str, args_raw: str) -> str:
        """把工具参数格式化为可读的确认摘要文本。

        按工具类型提取关键参数，避免直接展示原始 JSON。
        """
        # 解析参数
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
        except (json.JSONDecodeError, TypeError):
            args = {}

        lines = []
        if tool_name == "run_python_script":
            task = args.get("task", "")
            code = args.get("code", "")
            if task:
                lines.append(f"任务：{task}")
            if code:
                lines.append(f"代码：{code[:200]}{'…' if len(code) > 200 else ''}")
        elif tool_name == "call_mcp_tool":
            server = args.get("server", "")
            mcp_tool = args.get("tool", "")
            mcp_args = args.get("arguments", {})
            if server:
                lines.append(f"MCP 服务：{server}")
            if mcp_tool:
                lines.append(f"工具：{mcp_tool}")
            if mcp_args:
                try:
                    arg_str = json.dumps(mcp_args, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    arg_str = str(mcp_args)
                lines.append(f"参数：{arg_str[:300]}{'…' if len(arg_str) > 300 else ''}")
        elif tool_name == "run_skill":
            skill_id = args.get("skill_id", "")
            params = args.get("params", {})
            if skill_id:
                lines.append(f"技能 ID：{skill_id}")
            if params:
                try:
                    param_str = json.dumps(params, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    param_str = str(params)
                lines.append(f"参数：{param_str[:300]}{'…' if len(param_str) > 300 else ''}")
        else:
            # 通用回退：展示所有参数
            if args:
                try:
                    arg_str = json.dumps(args, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    arg_str = str(args)
                lines.append(f"参数：{arg_str[:400]}{'…' if len(arg_str) > 400 else ''}")
            else:
                lines.append("（无参数）")

        return "\n".join(lines) if lines else "（无参数）"

    def run(self, messages: List[Dict[str, Any]]):
        """生成器：yield {"type":"content"|"status"|"confirm"|"plan"|"done", ...}"""
        from lobster_mu.agent.hitl import confirm_manager
        from lobster_mu.agent.trace_store import log_trace

        result = ReActResult()
        working = list(messages)
        final_text = ""
        consecutive_failures = 0
        session_id = str(self.ctx.get("session_id", ""))

        for step in range(self.max_steps):
            yield {"type": "status", "text": f"第 {step + 1}/{self.max_steps} 步思考中…"}

            # 错误恢复：连续失败 ≥2 次时注入 retry_hint
            if consecutive_failures >= 2:
                hint = ("（系统提示：前面的工具调用连续失败。请检查参数是否正确，"
                        "或换一种思路/工具，必要时直接用文字回答用户。）\n")
                working.append({"role": "user", "content": hint})
                consecutive_failures = 0

            try:
                resp = self.adapter.chat_stream_with_tools(working, self.tools)
            except Exception as e:
                yield {"type": "content", "content": f"\n⚠️ 模型调用失败：{str(e)[:200]}\n"}
                result.final_text = final_text
                result.steps = step
                result.tool_calls_count = self.tool_calls_count
                yield {"type": "done", "result": result}
                return

            # 边读边 yield content 事件，实现真正的流式输出。
            # 流结束后检查 tool_calls：有工具调用时把已发的 content 标记为 thinking（前端修正）
            content_chunks: List[str] = []
            for chunk in resp:
                kind = chunk.get("type") if isinstance(chunk, dict) else None
                if kind == "content":
                    txt = chunk.get("content", "")
                    if txt and not txt.startswith("{\"__stats__\""):
                        content_chunks.append(txt)
                        yield {"type": "content", "content": txt}
                elif kind == "stats":
                    self._merge_stats(chunk.get("stats", {}))

            tool_calls = self._extract_tool_calls(resp)
            # 补全 id：assistant.tool_calls 与 role=tool 消息必须引用同一个 id
            for _i, _tc in enumerate(tool_calls):
                if not _tc.get("id"):
                    _tc["id"] = f"call_{self.tool_calls_count}_{_i}"
            # 中间步骤（有工具调用）：把已发的 content 修正为 thinking
            if tool_calls:
                yield {"type": "reclassify", "from": "content", "to": "thinking"}
            text_so_far = "".join(content_chunks)
            final_text += text_so_far
            log_trace(self.user_id, session_id, step + 1, "assistant", content=text_so_far[:2000])

            if not tool_calls:
                result.final_text = final_text
                result.steps = step + 1
                result.tool_calls_count = self.tool_calls_count
                result.token_stats = self.token_stats
                yield {"type": "done", "result": result}
                return

            working.append({
                "role": "assistant",
                "content": text_so_far or None,
                # 回灌给模型时必须使用 OpenAI 标准结构：function 为嵌套对象
                "tool_calls": [
                    {
                        "id": tc.get("id"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": tc.get("arguments") or "{}",
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # HITL：对 medium/high 工具发确认事件并等待回调
            for tc in tool_calls:
                spec = self.registry.get(tc.get("name", ""))
                if spec and (spec.hitl_required or spec.risk in ("medium", "high")):
                    rid = confirm_manager.request()
                    try:
                        args_raw = tc.get("arguments", "{}")
                        summary = self._format_confirm_summary(spec.name, args_raw)
                        yield {
                            "type": "confirm",
                            "request_id": rid,
                            "summary": summary,
                            "meta": {"tool": spec.name, "risk": spec.risk, "hitl": spec.hitl_required},
                        }
                        approved = confirm_manager.wait(rid, timeout=300)
                    finally:
                        confirm_manager.resolve(rid, False)
                    tc["_approved"] = approved

            # 执行工具前：把积压的状态文本（如"执行工具 X…"）推给前端
            yield from self._flush_status()
            observations = self._execute_tool_calls(tool_calls)
            # 工具执行完毕后再 flush 一次，确保状态全部送出
            yield from self._flush_status()

            step_all_failed = True
            for tc, obs in zip(tool_calls, observations):
                name = tc.get("name", "")
                args = tc.get("arguments", "")
                is_failure = any(k in obs for k in ("异常", "失败", "未确认", "未知工具", "错误", "未找到", "缺少"))
                log_trace(self.user_id, session_id, step + 1, "tool", tool_name=name,
                          arguments=args, content=obs[:2000], status="fail" if is_failure else "ok")
                if not is_failure:
                    step_all_failed = False
                # update_plan 工具：向前端推送计划事件
                if name == "update_plan" and not is_failure:
                    try:
                        a = json.loads(args) if isinstance(args, str) else (args or {})
                        yield {"type": "plan", "title": a.get("title", "执行计划"),
                               "steps": a.get("steps", [])}
                    except Exception:
                        pass
                working.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or f"{name}-{self.tool_calls_count}",
                    "content": obs[:20000],
                })

            consecutive_failures = consecutive_failures + 1 if step_all_failed and observations else 0

        result.final_text = final_text + "\n\n⚠️ 已达到最大执行步数，结果可能不完整。"
        result.steps = self.max_steps
        result.tool_calls_count = self.tool_calls_count
        result.truncated = True
        result.token_stats = self.token_stats
        yield {"type": "done", "result": result}

    def _execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[str]:
        """执行一批工具调用：low 风险并行，medium/high 串行；HITL 拦截。

        返回与 tool_calls 同序的 observation 列表。
        """
        if not tool_calls:
            return []

        results: List[Optional[str]] = [None] * len(tool_calls)
        parsed: List[Dict[str, Any]] = []
        for tc in tool_calls:
            raw = tc.get("arguments", "{}")
            try:
                args = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                args = {}
            parsed.append({"name": tc.get("name", ""), "args": args})

        # HITL：medium/high 已在 run() 中询问用户，读取 tc["_approved"]
        for i, p in enumerate(parsed):
            spec = self.registry.get(p["name"])
            if not spec:
                results[i] = f"未知工具：{p['name']}"
                continue
            if spec.hitl_required or spec.risk in ("medium", "high"):
                if not tool_calls[i].get("_approved", False):
                    results[i] = f"用户未确认执行工具 {p['name']}，已跳过"

        # 分组：low 且未确认跳过的 → 并行；其余 → 串行
        low_indices = [
            i for i, p in enumerate(parsed)
            if results[i] is None and self.registry[p["name"]].risk == "low"
        ]
        serial_indices = [
            i for i, p in enumerate(parsed)
            if results[i] is None and self.registry[p["name"]].risk != "low"
        ]

        # 并行执行 low 风险（受每用户 2 并发限制）
        user_sem = self._user_tool_sem(self.user_id)
        futures = {}
        for i in low_indices:
            spec = self.registry[parsed[i]["name"]]
            if not user_sem.acquire(timeout=5):
                results[i] = f"工具 {spec.name} 资源繁忙，已跳过"
                continue
            self.tool_calls_count += 1
            self.on_status(f"执行工具 {spec.name}…")
            fut = self._executor.submit(self._safe_exec, spec, parsed[i]["args"], user_sem)
            futures[fut] = i

        for fut, i in futures.items():
            results[i] = fut.result()

        # 串行执行 medium/high 风险
        for i in serial_indices:
            spec = self.registry[parsed[i]["name"]]
            self.tool_calls_count += 1
            self.on_status(f"执行工具 {spec.name}…")
            results[i] = self._safe_exec(spec, parsed[i]["args"], None)

        return results

    def _safe_exec(self, spec, args: Dict[str, Any], user_sem) -> str:
        try:
            return spec.executor(self.user_id, args)
        except Exception as e:
            return f"工具 {spec.name} 执行异常：{str(e)[:300]}"
        finally:
            if user_sem is not None:
                try:
                    user_sem.release()
                except Exception:
                    pass

    @staticmethod
    def _extract_tool_calls(resp) -> List[Dict[str, Any]]:
        """从 adapter 的流式响应中提取 tool_calls 列表。"""
        # adapter 应在响应结束时提供 tool_calls 聚合；若为可迭代且有 .tool_calls 属性
        tc = getattr(resp, "tool_calls", None)
        if tc:
            return tc
        # 否则从 chunks 中扫描（兼容某些实现把 tool_call 作为 chunk 发出）
        out: List[Dict[str, Any]] = []
        for c in resp._chunks if hasattr(resp, "_chunks") else []:
            if isinstance(c, dict) and c.get("type") in ("tool_call", "tool_calls"):
                out.extend(c.get("tool_calls", []))
        return out

    def _merge_stats(self, stats: Dict[str, Any]):
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self.token_stats[k] = self.token_stats.get(k, 0) + int(stats.get(k, 0) or 0)
