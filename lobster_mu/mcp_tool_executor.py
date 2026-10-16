# -*- coding: utf-8 -*-
"""MCP 服务端 - 配置化 API 封装工具执行器（{{param}} 模板渲染 + httpx 调用）"""
import json
import re
from typing import Any, Dict

import httpx

_TEMPLATE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
MAX_RESPONSE_CHARS = 20000


def render_template(text: str, params: Dict[str, Any]) -> str:
    """把 {{param}} 占位替换为调用参数值；缺失参数替换为空串。"""
    if not text:
        return ""
    def _sub(m):
        key = m.group(1)
        val = params.get(key, "")
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)
    return _TEMPLATE.sub(_sub, str(text))


def build_input_schema(params_schema: list) -> Dict[str, Any]:
    """由 params_schema 配置生成 MCP 工具的 JSON Schema（object）"""
    properties = {}
    required = []
    for p in params_schema or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        ptype = str(p.get("type") or "string")
        if ptype not in ("string", "number", "integer", "boolean", "array", "object"):
            ptype = "string"
        prop: Dict[str, Any] = {"type": ptype}
        if p.get("description"):
            prop["description"] = str(p["description"])
        if p.get("default") is not None:
            prop["default"] = p["default"]
        properties[str(p["name"])] = prop
        if p.get("required"):
            required.append(str(p["name"]))
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _validate_required(tool: Dict[str, Any], arguments: Dict[str, Any]) -> str:
    """校验 required 参数，返回错误信息（空串=通过）"""
    for p in tool.get("params_schema") or []:
        if isinstance(p, dict) and p.get("required") and p.get("name"):
            if arguments.get(p["name"]) in (None, ""):
                return f"缺少必填参数: {p['name']}"
    return ""


async def execute_api_tool(user_id: int, tool: Dict[str, Any], arguments: Dict[str, Any]) -> str:
    """执行配置化 API 工具，返回文本结果（含 HTTP 状态码，响应截断）"""
    args = dict(arguments or {})
    err = _validate_required(tool, args)
    if err:
        return f"参数错误: {err}"

    # 默认值回填
    for p in tool.get("params_schema") or []:
        if isinstance(p, dict) and p.get("name") and args.get(p["name"]) is None and p.get("default") is not None:
            args[p["name"]] = p["default"]

    url = render_template(tool.get("url") or "", args)
    if not url.startswith(("http://", "https://")):
        return f"配置错误: URL 非法 ({url[:100]})"
    method = str(tool.get("method") or "GET").upper()
    headers = {k: render_template(v, args) for k, v in (tool.get("headers") or {}).items()}
    query = {k: render_template(v, args) for k, v in (tool.get("query_params") or {}).items()}
    body_raw = render_template(tool.get("body_template") or "", args)
    timeout = max(1, min(300, int(tool.get("timeout") or 30)))

    try:
        # 注意：httpx 传 params={}（空dict）会丢弃 URL 中已有 query，故为空时传 None
        qp = query or None
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method in ("GET", "DELETE"):
                resp = await client.request(method, url, params=qp, headers=headers)
            else:
                payload: Any = body_raw
                if body_raw.strip():
                    try:
                        payload = json.loads(body_raw)
                    except Exception:
                        payload = body_raw
                    if isinstance(payload, (dict, list)):
                        resp = await client.request(method, url, params=qp, headers=headers, json=payload)
                    else:
                        resp = await client.request(method, url, params=qp, headers=headers, content=payload)
                else:
                    resp = await client.request(method, url, params=qp, headers=headers)
        text = resp.text[:MAX_RESPONSE_CHARS]
        if len(resp.text) > MAX_RESPONSE_CHARS:
            text += f"\n...(响应已截断，共 {len(resp.text)} 字符)"
        return f"HTTP {resp.status_code}\n{text}"
    except httpx.TimeoutException:
        return f"调用失败: 请求超时（{timeout}s）"
    except Exception as e:
        return f"调用失败: {e}"
