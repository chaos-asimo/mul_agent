# -*- coding: utf-8 -*-
"""Agent 编排引擎（ReAct 循环 + 统一工具注册表 + HITL + 轨迹）"""
from .tool_registry import (
    TOOL_REGISTRY, ToolSpec, get_tool_schema_list,
    register_sub_agent_cancel, cancel_sub_agent,
)
from .loop import ReActLoop, ReActResult
from .hitl import confirm_manager
from .trace_store import log_trace, list_traces

__all__ = [
    "TOOL_REGISTRY", "ToolSpec", "get_tool_schema_list",
    "ReActLoop", "ReActResult", "confirm_manager",
    "register_sub_agent_cancel", "cancel_sub_agent",
    "log_trace", "list_traces",
]
