# -*- coding: utf-8 -*-
"""对外 API 统一认证依赖（双轨：API Key 或 session 登录）

校验顺序（满足其一即放行）：
  1. 请求头 X-API-Key 命中环境变量 API_KEYS（逗号分隔，支持多 key）
  2. session 中存在已登录用户（user 或 mu_user 键）

安全策略：
  - 未配置 API_KEYS 且无有效 session → 401（默认拒绝）
  - API Key 比较使用 hmac.compare_digest 防时序攻击
"""
import hmac
import os

from fastapi import Request, HTTPException

# 缓存环境变量解析结果（每次请求读取，便于运行时改 env 生效）
def _load_api_keys() -> set:
    raw = os.environ.get("API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


async def require_auth(request: Request):
    """对外 API 认证依赖。可用方式：router 级 dependencies=[Depends(require_auth)] 或端点级 Depends。"""
    # 1) API Key（X-API-Key 请求头）
    api_keys = _load_api_keys()
    if api_keys:
        provided = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        if provided:
            for key in api_keys:
                if hmac.compare_digest(provided, key):
                    return {"auth": "api_key"}
            # 提供了 key 但无效 → 直接拒绝（不继续 fallback，避免 key 被爆破时泄露 session 状态）
            raise HTTPException(status_code=401, detail="无效的 API Key")

    # 2) session 登录（v1 用 "user"，v3 多用户用 "mu_user"）
    session = getattr(request, "session", None)
    if session:
        user = session.get("user") or session.get("mu_user")
        if user:
            return {"auth": "session", "user": user}

    # 3) 均未通过
    if not api_keys:
        raise HTTPException(status_code=401, detail="未认证：请配置 API_KEYS 环境变量后通过 X-API-Key 头访问，或登录后使用 session 访问")
    raise HTTPException(status_code=401, detail="未认证：API Key 无效且未登录")
