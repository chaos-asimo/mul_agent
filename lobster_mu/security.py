# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 认证与安全（pbkdf2 密码哈希 + FastAPI 依赖注入）"""
import hashlib
import hmac
import secrets

from fastapi import Request, HTTPException, Depends

from lobster_mu import user_store

PBKDF2_ITERATIONS = 200000


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()


def new_salt() -> str:
    return secrets.token_hex(16)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)


def get_mu_user(request: Request) -> dict:
    """每个龙虾-mu 端点的用户依赖：user_id 由此贯穿所有数据操作"""
    u = request.session.get("mu_user")
    if not u:
        raise HTTPException(status_code=401, detail="未登录")
    if user_store.is_disabled(u["id"]):
        request.session.pop("mu_user", None)
        raise HTTPException(status_code=401, detail="账号已禁用")
    return u


def require_admin(user: dict = Depends(get_mu_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
