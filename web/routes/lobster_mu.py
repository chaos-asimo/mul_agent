# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 路由层（前缀 /api/lobster-mu）"""
import os
import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile, Form, Body
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

from lobster_mu import db, user_store, tools
from lobster_mu.security import verify_password, get_mu_user, require_admin

import pyotp
import qrcode
import io
import base64
import json as _json
import time as _time2
import logging as _logging
import hashlib
import hmac

router = APIRouter(prefix="/api/lobster-mu")

_db_ready = False


def get_client_ip(request) -> str:
    """获取真实客户端 IP：经 nginx 反代时，优先读转发头。
    X-Real-IP 最可信（nginx 用 $remote_addr 覆盖，客户端无法伪造）；
    其次 X-Forwarded-For 取最左（原始客户端）；最后回退直连 IP。"""
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def ensure_db():
    """惰性初始化数据库与默认管理员（首次请求或模块导入后触发）"""
    global _db_ready
    if not _db_ready:
        db.init_db()
        user_store.init_users()
        _db_ready = True


# ============ 认证 ============

class MuLoginRequest(BaseModel):
    username: str
    password: str


class MuTwoFactorRequest(BaseModel):
    username: str
    totp: str


class TOTPConfirmRequest(BaseModel):
    totp: str


class TOTPDisableRequest(BaseModel):
    password: str


# ---- 登录速率限制（IP+账户组合，防暴力破解） ----
import time as _time

class LoginRateLimiter:
    """基于 IP+账户 组合的登录失败计数 + 锁定

    - 同一 IP 登录同一账户，15 分钟内失败超过 MAX_FAILS 次 → 锁定 LOCK_SECONDS 秒
    - 不同账户、不同 IP 分别计数，互不影响
    - 锁定期间该 IP+账户组合直接返回 429
    """
    MAX_FAILS = 5
    WINDOW = 900      # 15 分钟
    LOCK_SECONDS = 900  # 锁定 15 分钟

    @staticmethod
    def _key(ip: str, username: str) -> str:
        return f"{ip}:{username}"

    def __init__(self):
        self._fails: Dict[str, list] = {}      # "ip:username" -> [timestamps]
        self._locks: Dict[str, float] = {}     # "ip:username" -> 解锁时间戳

    def check(self, ip: str, username: str):
        """锁定中则抛 429，否则返回剩余重试次数（供响应头使用）"""
        if not ip:
            return self.MAX_FAILS
        key = self._key(ip, username)
        now = _time.time()
        # 检查锁定
        unlock_at = self._locks.get(key, 0)
        if now < unlock_at:
            remaining = int(unlock_at - now)
            raise HTTPException(
                status_code=429,
                detail=f"登录失败次数过多，请 {remaining} 秒后重试",
            )
        # 检查窗口内失败次数
        bucket = [t for t in self._fails.get(key, []) if now - t < self.WINDOW]
        self._fails[key] = bucket
        if len(bucket) >= self.MAX_FAILS:
            self._locks[key] = now + self.LOCK_SECONDS
            self._fails[key] = []
            remaining = self.LOCK_SECONDS
            raise HTTPException(
                status_code=429,
                detail=f"登录失败次数过多，已锁定 {remaining // 60} 分钟",
            )
        return self.MAX_FAILS - len(bucket)

    def record_failure(self, ip: str, username: str):
        if not ip:
            return
        key = self._key(ip, username)
        now = _time.time()
        bucket = [t for t in self._fails.get(key, []) if now - t < self.WINDOW]
        bucket.append(now)
        self._fails[key] = bucket

    def record_success(self, ip: str, username: str):
        if ip:
            key = self._key(ip, username)
            self._fails.pop(key, None)
            self._locks.pop(key, None)

    def cleanup(self):
        """定期清理过期的失败记录和锁定（防止内存泄漏）"""
        now = _time.time()
        expired_keys = [
            k for k, t in self._locks.items() if now >= t
        ]
        for k in expired_keys:
            self._locks.pop(k, None)
        # 清理窗口外的失败记录
        for k in list(self._fails.keys()):
            self._fails[k] = [t for t in self._fails[k] if now - t < self.WINDOW]
            if not self._fails[k]:
                self._fails.pop(k, None)


login_limiter = LoginRateLimiter()

# TOTP 登录 pending 存储（用户名 → {user_id, expires_at}）
_totp_pending: Dict[str, dict] = {}
_TOTP_PENDING_TTL = 300  # 5 分钟

# TOTP 绑定 pending 存储（user_id → {secret, expires_at}）
_totp_bind_pending: Dict[int, dict] = {}
_TOTP_BIND_TTL = 300  # 5 分钟


def _cleanup_totp_pending():
    now = _time.time()
    for k in list(_totp_pending):
        if _totp_pending[k]["expires_at"] < now:
            del _totp_pending[k]
    for k in list(_totp_bind_pending):
        if _totp_bind_pending[k]["expires_at"] < now:
            del _totp_bind_pending[k]


def _verify_totp_code(secret: str, code: str) -> bool:
    """验证 TOTP 6 位码（pyotp 标准，window=1 允许 ±30s 容差）"""
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


@router.post("/login")
async def mu_login(request: Request, body: MuLoginRequest):
    ensure_db()
    ip = get_client_ip(request)
    # 速率限制检查（IP+账户组合）
    login_limiter.check(ip, body.username)
    row = user_store.get_by_username(body.username)
    if not row or row["disabled"] or not verify_password(body.password, row["salt"], row["password_hash"]):
        login_limiter.record_failure(ip, body.username)
        tools.log_operation(0, "login_failed", f"用户 {body.username} 登录失败", success=False, ip=ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    login_limiter.record_success(ip, body.username)

    # TOTP 已启用：不直接登录，返回 needs_2fa
    if row["totp_enabled"] and row["totp_secret"]:
        _cleanup_totp_pending()
        _totp_pending[row["username"]] = {
            "user_id": row["id"],
            "expires_at": _time.time() + _TOTP_PENDING_TTL,
        }
        tools.log_operation(row["id"], "login_2fa_required",
                            f"{row['username']} 需二次验证", ip=ip)
        return {"status": "needs_2fa", "username": row["username"],
                "totp": {"issuer": "LobsterClaw", "label": row["username"]}}

    # 未启用 TOTP：直接登录
    request.session["mu_user"] = {"id": row["id"], "username": row["username"], "role": row["role"], "display_name": row["display_name"] or row["username"]}
    user_store.update_last_login(row["id"], request.headers.get("user-agent") or None)
    tools.log_operation(row["id"], "login", f"{row['username']} 登录成功", ip=ip)
    return {"status": "success", "user": {"id": row["id"], "username": row["username"], "role": row["role"], "display_name": row["display_name"] or row["username"]}}


@router.post("/login/2fa")
async def mu_login_2fa(request: Request, body: MuTwoFactorRequest):
    ensure_db()
    ip = get_client_ip(request)
    login_limiter.check(ip, body.username)
    _cleanup_totp_pending()
    pending = _totp_pending.get(body.username)
    if not pending or pending["expires_at"] < _time.time():
        raise HTTPException(status_code=400, detail="二次验证已过期，请重新登录")
    row = user_store.get_by_id(pending["user_id"])
    if not row or row["disabled"]:
        raise HTTPException(status_code=403, detail="账号已禁用")
    if not _verify_totp_code(row["totp_secret"], body.totp.strip()):
        login_limiter.record_failure(ip, body.username)
        tools.log_operation(row["id"], "login_2fa_failed",
                            f"{row['username']} 二次验证失败", success=False, ip=ip)
        raise HTTPException(status_code=401, detail="验证码错误")
    # 验证通过，清除 pending + 登录
    del _totp_pending[body.username]
    login_limiter.record_success(ip, body.username)
    request.session.pop("mu_2fa_pending", None)
    request.session["mu_user"] = {"id": row["id"], "username": row["username"], "role": row["role"], "display_name": row["display_name"] or row["username"]}
    user_store.update_last_login(row["id"], request.headers.get("user-agent") or None)
    tools.log_operation(row["id"], "login_2fa_success",
                        f"{row['username']} 二次验证登录成功", ip=ip)
    return {"status": "success", "user": {"id": row["id"], "username": row["username"], "role": row["role"], "display_name": row["display_name"] or row["username"]}}


# ============ TOTP 绑定/解绑 ============

def _totp_status(user_id: int) -> dict:
    row = user_store.get_by_id(user_id)
    return {"enabled": bool(row["totp_enabled"]) if row else False}


@router.get("/totp/status")
async def mu_totp_status(user: dict = Depends(get_mu_user)):
    ensure_db()
    return _totp_status(user["id"])


@router.post("/totp/setup")
async def mu_totp_setup(user: dict = Depends(get_mu_user)):
    ensure_db()
    """生成 TOTP 密钥 + QR 码（base64 PNG），保存到 pending 存储。
    前端展示 QR 码，用户输入 6 位码后调 /totp/confirm 验证。"""
    username = user["username"]
    secret = pyotp.random_base32()
    provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="LobsterClaw")
    # 生成 QR 码 base64 PNG
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    # 保存到 pending（5 分钟内有效）
    _cleanup_totp_pending()
    _totp_bind_pending[user["id"]] = {"secret": secret, "expires_at": _time.time() + _TOTP_BIND_TTL}
    return {
        "status": "pending",
        "qr": f"data:image/png;base64,{qr_b64}",
        "secret": secret,
        "provisioning_uri": provisioning_uri,
        "issuer": "LobsterClaw",
        "label": username,
        "ttl": _TOTP_BIND_TTL,
    }


@router.post("/totp/confirm")
async def mu_totp_confirm(request: Request, body: TOTPConfirmRequest, user: dict = Depends(get_mu_user)):
    ensure_db()
    ip = get_client_ip(request)
    _cleanup_totp_pending()
    pending = _totp_bind_pending.get(user["id"])
    if not pending or pending["expires_at"] < _time.time():
        raise HTTPException(status_code=400, detail="绑定已过期，请重新生成")
    if not _verify_totp_code(pending["secret"], body.totp.strip()):
        tools.log_operation(user["id"], "totp_confirm_failed",
                            f"{user['username']} TOTP 确认码错误", success=False, ip=ip)
        raise HTTPException(status_code=401, detail="验证码错误，请重试")
    # 验证通过，正式启用
    user_store.set_totp_secret(user["id"], pending["secret"])
    user_store.enable_totp(user["id"])
    del _totp_bind_pending[user["id"]]
    tools.log_operation(user["id"], "totp_enabled",
                        f"{user['username']} 启用微软 Authenticator", ip=ip)
    return {"status": "success", "message": "已启用微软 Authenticator"}


@router.post("/totp/disable")
async def mu_totp_disable(request: Request, body: TOTPDisableRequest, user: dict = Depends(get_mu_user)):
    ensure_db()
    ip = get_client_ip(request)
    row = user_store.get_by_id(user["id"])
    if not row or not row["totp_enabled"]:
        raise HTTPException(status_code=400, detail="TOTP 未启用")
    if not verify_password(body.password, row["salt"], row["password_hash"]):
        tools.log_operation(user["id"], "totp_disable_failed",
                            f"{user['username']} 解绑密码错误", success=False, ip=ip)
        raise HTTPException(status_code=401, detail="密码错误")
    user_store.disable_totp(user["id"])
    tools.log_operation(user["id"], "totp_disabled",
                        f"{user['username']} 关闭微软 Authenticator", ip=ip)
    return {"status": "success", "message": "已关闭微软 Authenticator"}


@router.post("/logout")
async def mu_logout(request: Request):
    u = request.session.get("mu_user")
    uid = u["id"] if u else 0
    username = u["username"] if u else ""
    ip = get_client_ip(request)
    if u:
        tools.log_operation(uid, "logout", f"{username} 退出登录", ip=ip)
    request.session.pop("mu_user", None)
    request.session.pop("mu_2fa_pending", None)
    return {"status": "success", "message": "退出成功"}


# ============ 直接登录（按用户名/显示名，不存在则自动创建） ============

# 平台 token 身份校验接口（内网），可用环境变量覆盖
PLATFORM_TOKEN_VERIFY_URL = os.environ.get(
    "PLATFORM_TOKEN_VERIFY_URL",
    "http://10.111.1.250:32516/PT/business/token/getUserInfoViaToken",
)
# 校验失败时是否拒绝登录（默认拒绝；仅调试时可设 false 放行）
PLATFORM_TOKEN_VERIFY_STRICT = os.environ.get("PLATFORM_TOKEN_VERIFY_STRICT", "true").lower() != "false"


def _verify_platform_token(token: str, username: str) -> "tuple[bool, str]":
    """调用平台 token 校验接口，确认 token 对应用户(grbh)与登录 username 一致（本人操作）。
    返回 (ok, 失败原因)。同步阻塞，调用方须用 asyncio.to_thread 包装。"""
    import requests as _requests
    try:
        resp = _requests.get(PLATFORM_TOKEN_VERIFY_URL, params={"token": token}, timeout=8)
    except Exception as e:
        return False, f"平台校验服务不可达: {e}"
    if resp.status_code != 200:
        return False, f"平台校验服务返回 HTTP {resp.status_code}"
    try:
        data = resp.json()
    except Exception:
        return False, "平台校验服务返回非 JSON"
    if data.get("valid") is not True or data.get("tokenState") != 0:
        return False, "平台 token 无效或已过期"
    grbh = str(data.get("grbh") or "").strip()
    if not grbh:
        return False, "平台返回缺少 grbh 字段"
    if grbh != str(username).strip():
        return False, "token 对应用户与登录用户名不一致"
    return True, ""


class MuDirectLoginRequest(BaseModel):
    username: str
    display_name: str
    login_token: Optional[str] = None  # 平台登录 token，存入 session 供调用平台能力


@router.post("/login/direct")
async def mu_login_direct(request: Request, body: MuDirectLoginRequest):
    """按用户名直接登录；若用户不存在则自动新建（密码固定为 用户名+sy），已存在则直接登录。

    来源校验：环境变量 DIRECT_LOGIN_ALLOWED_ORIGINS 配置允许的 Origin 列表（逗号分隔）。
    若未配置则禁止跨域调用（仅允许同源请求）。
    """
    # ---- 来源校验（支持 * 通配符，如 *.jbysoft.com）----
    allowed_origins = [o.strip().lower() for o in os.environ.get("DIRECT_LOGIN_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()

    def _origin_allowed(o: str) -> bool:
        for a in allowed_origins:
            if a == o:
                return True
            if a.startswith("*."):
                if o.endswith(a[1:]):  # *.jbysoft.com → .jbysoft.com
                    return True
        return False

    # Origin 为 null（file:// 打开 HTML）→ 放行，记录日志
    if origin == "null":
        tools.log_operation(0, "login_direct_file", f"file:// 请求（Origin=null）", ip=get_client_ip(request))
    elif origin:
        # 有 Origin 且非 null → 跨域请求
        if allowed_origins:
            if _origin_allowed(origin):
                pass  # 允许
            else:
                tools.log_operation(0, "login_direct_blocked", f"来源被拒绝: {origin}", success=False,
                                    ip=get_client_ip(request))
                raise HTTPException(status_code=403, detail="来源不被允许")
        else:
            # 未配置允许列表 → 拒绝所有跨域请求
            tools.log_operation(0, "login_direct_blocked", f"跨域请求被拒绝(未配置允许列表): {origin}", success=False,
                                ip=get_client_ip(request))
            raise HTTPException(status_code=403, detail="来源不被允许")
    # origin 为空（同源请求）→ 放行
    if not origin and referer:
        tools.log_operation(0, "login_direct_referer", f"Referer: {referer}", ip=get_client_ip(request))

    ensure_db()
    username = (body.username or "").strip()
    display_name = (body.display_name or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not display_name:
        raise HTTPException(status_code=400, detail="显示名不能为空")

    # ---- 平台身份校验：携带 login_token 时，调用平台接口确认 token 对应用户(grbh)
    # 与 username 一致（本人操作）。校验失败一律拒绝，防止冒用他人身份直登。----
    if body.login_token:
        ok, why = await asyncio.to_thread(_verify_platform_token, body.login_token, username)
        if not ok:
            tools.log_operation(0, "login_direct_token_denied",
                                f"{username} 平台token校验失败: {why}",
                                success=False, ip=get_client_ip(request))
            if PLATFORM_TOKEN_VERIFY_STRICT:
                raise HTTPException(status_code=403, detail=f"身份校验失败: {why}")
        else:
            tools.log_operation(0, "login_direct_token_ok",
                                f"{username} 平台token校验通过", ip=get_client_ip(request))

    row = user_store.get_by_username(username)
    created = False
    if not row:
        # 不存在则新建用户，密码为 用户名+sy
        password = f"{username}sy"
        try:
            uid = user_store.create_user(username, password, "user", display_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        row = user_store.get_by_id(uid)
        created = True
    else:
        # 已存在用户，更新显示名
        user_store.update_user(row["id"], display_name=display_name)

    if row["disabled"]:
        tools.log_operation(0, "login_failed", f"已禁用用户 {username} 尝试登录", success=False,
                            ip=get_client_ip(request))
        raise HTTPException(status_code=403, detail="账号已禁用")

    ip = get_client_ip(request)

    # 已启用微软 Authenticator：建立“待二次验证”受限会话，返回 success 让外部页面跳转，
    # 跳转后由前端接管弹出验证窗口；受限会话不授予业务访问权（get_mu_user 会拦截）
    if row["totp_enabled"] and row["totp_secret"]:
        _cleanup_totp_pending()
        _totp_pending[row["username"]] = {
            "user_id": row["id"],
            "expires_at": _time.time() + _TOTP_PENDING_TTL,
        }
        tools.log_operation(row["id"], "login_2fa_required",
                            f"{row['username']} direct 登录需二次验证", ip=ip)
        pending_user = {"id": row["id"], "username": row["username"], "role": row["role"],
                        "display_name": row["display_name"] or row["username"]}
        # 关键：必须清除可能残留的 mu_user（用户之前登录过、cookie 仍有效时），
        # 否则 /me 会优先返回 mu_user 而看不到 needs_2fa，导致 2FA 被绕过、直接进工作台
        request.session.pop("mu_user", None)
        request.session["mu_2fa_pending"] = pending_user
        if body.login_token:
            request.session["mu_login_token"] = body.login_token
        user_store.update_last_login(row["id"], request.headers.get("user-agent") or None)
        return {"status": "success", "user": pending_user, "needs_2fa": True, "created": created}

    request.session.pop("mu_2fa_pending", None)
    request.session["mu_user"] = {"id": row["id"], "username": row["username"], "role": row["role"], "display_name": row["display_name"] or row["username"]}
    if body.login_token:
        request.session["mu_login_token"] = body.login_token
    user_store.update_last_login(row["id"], request.headers.get("user-agent") or None)
    tools.log_operation(row["id"], "login", f"{row['username']} 登录成功" + ("（自动创建账号）" if created else ""), ip=ip)
    return {
        "status": "success",
        "user": {"id": row["id"], "username": row["username"], "role": row["role"], "display_name": row["display_name"] or row["username"]},
        "created": created,
    }


@router.get("/me")
async def mu_me(request: Request):
    """返回当前登录态。优先识别“待二次验证”受限会话（mu_2fa_pending），
    避免残留的 mu_user 遮蔽 2FA 需求导致绕过；受限会话不携带 mu_user，
    其余业务接口会被 get_mu_user 拦截。"""
    pending = request.session.get("mu_2fa_pending")
    if pending:
        return {"user": pending, "needs_2fa": True}
    u = request.session.get("mu_user")
    if u:
        if user_store.is_disabled(u["id"]):
            request.session.pop("mu_user", None)
            raise HTTPException(status_code=401, detail="账号已禁用")
        return {"user": u}
    raise HTTPException(status_code=401, detail="未登录")


# ============ 管理员用户管理（仅管理员创建账号） ============

class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"
    display_name: str = ""


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    display_name: Optional[str] = None
    disabled: Optional[bool] = None
    new_password: Optional[str] = None


class SuggestionCreate(BaseModel):
    content: str


class SuggestionReply(BaseModel):
    reply: str


@router.get("/admin/users")
async def admin_list_users(admin: dict = Depends(require_admin)):
    _t0 = _time2.perf_counter()
    ensure_db()
    _t1 = _time2.perf_counter()
    users = user_store.list_users()
    _t2 = _time2.perf_counter()
    # 分段计时：与 ApiAccessLogMiddleware 记录的请求总耗时对比，
    # 差值即为请求在到达 handler 前的排队/事件循环阻塞时间。
    _logging.getLogger("lobster_mu").info(
        "[perf] /admin/users ensure_db=%.3fms list_users=%.3fms handler_total=%.3fms",
        (_t1 - _t0) * 1000, (_t2 - _t1) * 1000, (_t2 - _t0) * 1000,
    )
    return {"users": users}


@router.post("/admin/users")
async def admin_create_user(body: AdminUserCreate, admin: dict = Depends(require_admin)):
    ensure_db()
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="角色必须为 admin 或 user")
    if not body.username or not body.password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    try:
        uid = user_store.create_user(body.username, body.password, body.role, body.display_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "id": uid}


@router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: int, body: AdminUserUpdate, admin: dict = Depends(require_admin)):
    ensure_db()
    if body.role is not None and body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="角色必须为 admin 或 user")
    # 防止禁用/降级最后一个可用管理员
    if (body.disabled or (body.role == "user")) and user_store.count_admins_excluding(user_id) == 0:
        row = user_store.get_by_id(user_id)
        if row and row["role"] == "admin" and not row["disabled"]:
            raise HTTPException(status_code=400, detail="不能禁用或降级最后一个可用管理员")
    ok = user_store.update_user(user_id, body.role, body.display_name, body.disabled, body.new_password)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 禁用即踢会话：下次请求 get_mu_user 会因 is_disabled 拒绝
    return {"status": "success"}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: int, admin: dict = Depends(require_admin)):
    ensure_db()
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    if user_store.count_admins_excluding(user_id) == 0:
        row = user_store.get_by_id(user_id)
        if row and row["role"] == "admin" and not row["disabled"]:
            raise HTTPException(status_code=400, detail="不能删除最后一个可用管理员")
    ok = user_store.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"status": "success"}


@router.post("/admin/users/{user_id}/totp/disable")
async def admin_disable_user_totp(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """管理员强制解绑指定用户的微软 Authenticator 两步认证（无需该用户密码）。
    用于用户丢失手机/换设备后无法自助解绑的场景。"""
    ensure_db()
    row = user_store.get_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not row["totp_enabled"]:
        raise HTTPException(status_code=400, detail="该用户未启用两步认证")
    ip = get_client_ip(request)
    user_store.disable_totp(user_id)
    tools.log_operation(admin["id"], "admin:totp_disabled",
                        f"管理员解绑用户 {row['username']} 的两步认证", ip=ip)
    return {"status": "success", "message": f"已解绑 {row['username']} 的两步认证"}


@router.get("/admin/users/{user_id}/sessions")
async def admin_list_user_sessions(user_id: int, admin: dict = Depends(require_admin)):
    """管理员查看指定用户的聊天会话列表"""
    ensure_db()
    row = user_store.get_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "sessions": session_store.list_sessions(user_id), "username": row["username"]}


@router.get("/admin/users/{user_id}/sessions/{session_id}/messages")
async def admin_get_session_messages(user_id: int, session_id: str, admin: dict = Depends(require_admin)):
    """管理员查看指定用户的指定会话消息"""
    ensure_db()
    msgs = session_store.get_messages(user_id, session_id)
    if msgs is None:
        return {"success": False, "error": "会话不存在"}
    return {"success": True, "session": {"id": session_id, "messages": msgs}}


# ============ 管理员日志管理 ============

@router.get("/admin/logs")
async def admin_list_logs(
    user_id: Optional[int] = None,
    operation: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    """管理员查询操作日志（可按用户/操作类型筛选，分页）"""
    ensure_db()
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    where = "1=1"
    params: list = []
    if user_id is not None:
        where += " AND l.user_id = ?"
        params.append(user_id)
    if operation:
        where += " AND l.operation = ?"
        params.append(operation)
    conn = db.get_conn()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) c FROM mu_operation_logs l WHERE {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT l.id, l.user_id, l.operation, l.detail, l.success, l.ip, l.created_at, u.username, u.display_name "
            f"FROM mu_operation_logs l LEFT JOIN users u ON u.id = l.user_id "
            f"WHERE {where} ORDER BY l.id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()
    logs = [dict(r) for r in rows]
    for log in logs:
        # user_id=0 为登录失败等无归属记录
        log["username"] = log["username"] or (f"未知用户({log['user_id']})" if log["user_id"] else "未记录")
        log["display_name"] = log.get("display_name") or log["username"]
    return {"success": True, "logs": logs, "total": total}


@router.delete("/admin/logs/{record_id}")
async def admin_delete_log(record_id: int, admin: dict = Depends(require_admin)):
    """管理员删除单条日志"""
    ensure_db()
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM mu_operation_logs WHERE id = ?", (record_id,))
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()
    if ok:
        tools.log_operation(admin["id"], "admin:delete_log", f"删除日志 #{record_id}")
    return {"success": ok}


@router.delete("/admin/logs")
async def admin_clear_logs(
    user_id: Optional[int] = None,
    admin: dict = Depends(require_admin),
):
    """管理员清空日志（可按用户）"""
    ensure_db()
    conn = db.get_conn()
    try:
        if user_id is not None:
            cur = conn.execute("DELETE FROM mu_operation_logs WHERE user_id = ?", (user_id,))
        else:
            cur = conn.execute("DELETE FROM mu_operation_logs")
        conn.commit()
        deleted = cur.rowcount
    finally:
        conn.close()
    scope = f"用户 {user_id}" if user_id is not None else "全部"
    tools.log_operation(admin["id"], "admin:clear_logs", f"清空{scope}日志（{deleted} 条）")
    return {"success": True, "deleted": deleted}


# ============ 接口访问日志（仅管理员） ============

@router.get("/admin/api-access-logs")
async def admin_api_access_logs(
    user_id: Optional[int] = None,
    path: Optional[str] = None,
    status: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    """管理员查询接口访问日志（可按用户/路径/状态码/时间范围筛选，分页）"""
    _t0 = _time2.perf_counter()
    ensure_db()
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    where = "1=1"
    params: list = []
    if user_id is not None:
        where += " AND l.user_id = ?"
        params.append(user_id)
    if path:
        where += " AND l.path LIKE ?"
        params.append(f"%{path}%")
    if status is not None:
        where += " AND l.status = ?"
        params.append(status)
    if start_time:
        where += " AND l.created_at >= ?"
        params.append(start_time)
    if end_time:
        where += " AND l.created_at <= ?"
        params.append(end_time)
    conn = db.get_conn()
    _t1 = _time2.perf_counter()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) c FROM mu_api_access_logs l WHERE {where}", params
        ).fetchone()["c"]
        _t2 = _time2.perf_counter()
        rows = conn.execute(
            f"SELECT l.id, l.method, l.path, l.status, l.duration_ms, l.ip, l.username, l.user_id, l.auth_type, l.created_at, u.display_name "
            f"FROM mu_api_access_logs l LEFT JOIN users u ON u.id = l.user_id "
            f"WHERE {where} ORDER BY l.id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        _t3 = _time2.perf_counter()
    finally:
        conn.close()
    _logging.getLogger("lobster_mu").info(
        "[perf] /admin/api-access-logs get_conn=%.1fms count=%.1fms select=%.1fms total=%.1fms",
        (_t1 - _t0) * 1000, (_t2 - _t1) * 1000, (_t3 - _t2) * 1000, (_t3 - _t0) * 1000,
    )
    logs = [dict(r) for r in rows]
    for log in logs:
        log["display_name"] = log.get("display_name") or log.get("username") or "-"
    return {"success": True, "logs": logs, "total": total}


@router.delete("/admin/api-access-logs/{log_id}")
async def admin_delete_api_log(log_id: int, admin: dict = Depends(require_admin)):
    """管理员删除单条接口访问日志"""
    ensure_db()
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM mu_api_access_logs WHERE id = ?", (log_id,))
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()
    if ok:
        tools.log_operation(admin["id"], "admin:delete_api_log", f"删除接口日志 #{log_id}")
    return {"success": ok}


@router.delete("/admin/api-access-logs")
async def admin_clear_api_logs(
    user_id: Optional[int] = None,
    admin: dict = Depends(require_admin),
):
    """管理员清空接口访问日志（可按用户）"""
    ensure_db()
    conn = db.get_conn()
    try:
        if user_id is not None:
            cur = conn.execute("DELETE FROM mu_api_access_logs WHERE user_id = ?", (user_id,))
        else:
            cur = conn.execute("DELETE FROM mu_api_access_logs")
        conn.commit()
        deleted = cur.rowcount
    finally:
        conn.close()
    scope = f"用户 {user_id}" if user_id is not None else "全部"
    tools.log_operation(admin["id"], "admin:clear_api_logs", f"清空{scope}接口访问日志（{deleted} 条）")
    return {"success": True, "deleted": deleted}


# ============ 日志保留策略（管理员可在界面开关/调阈值，后台每日自动清理） ============

# 默认阈值（与 README/文档一致）：接口日志 14 天且≤10 万行；操作日志 180 天且≤20 万行
_LOGRET_DEFAULTS = {
    "enabled": "0",          # 默认关闭，需管理员在界面开启
    "api_days": "14",
    "api_max_rows": "100000",
    "op_days": "180",
    "op_max_rows": "200000",
}
_LOGRET_KEYS = ("enabled", "api_days", "api_max_rows", "op_days", "op_max_rows")


def get_logret_settings() -> dict:
    """读取日志保留配置（缺失项回退默认值），返回带类型的 dict"""
    ensure_db()
    raw = {k: db.get_config(f"logret.{k}", _LOGRET_DEFAULTS[k]) for k in _LOGRET_KEYS}
    def _i(v, default):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    return {
        "enabled": str(raw["enabled"]) in ("1", "true", "True", "on"),
        "api_days": _i(raw["api_days"], 14),
        "api_max_rows": _i(raw["api_max_rows"], 100000),
        "op_days": _i(raw["op_days"], 180),
        "op_max_rows": _i(raw["op_max_rows"], 200000),
    }


def run_log_retention() -> dict:
    """执行一次日志清理（按时间 + 按行数上限）。返回各表删除条数。
    供后台每日循环与管理员手动触发共用；无论开关与否都可手动运行。"""
    ensure_db()
    s = get_logret_settings()
    from datetime import timedelta
    result = {"api_deleted": 0, "op_deleted": 0}
    conn = db.get_conn()
    try:
        # 接口访问日志
        cutoff = (datetime.now() - timedelta(days=max(0, s["api_days"]))).isoformat()
        cur = conn.execute("DELETE FROM mu_api_access_logs WHERE created_at < ?", (cutoff,))
        result["api_deleted"] += cur.rowcount or 0
        if s["api_max_rows"] > 0:
            cur = conn.execute(
                "DELETE FROM mu_api_access_logs WHERE id NOT IN "
                "(SELECT id FROM mu_api_access_logs ORDER BY id DESC LIMIT ?)",
                (s["api_max_rows"],),
            )
            result["api_deleted"] += cur.rowcount or 0
        # 操作日志
        cutoff = (datetime.now() - timedelta(days=max(0, s["op_days"]))).isoformat()
        cur = conn.execute("DELETE FROM mu_operation_logs WHERE created_at < ?", (cutoff,))
        result["op_deleted"] += cur.rowcount or 0
        if s["op_max_rows"] > 0:
            cur = conn.execute(
                "DELETE FROM mu_operation_logs WHERE id NOT IN "
                "(SELECT id FROM mu_operation_logs ORDER BY id DESC LIMIT ?)",
                (s["op_max_rows"],),
            )
            result["op_deleted"] += cur.rowcount or 0
        conn.commit()
    finally:
        conn.close()
    return result


class LogRetentionConfig(BaseModel):
    enabled: Optional[bool] = None
    api_days: Optional[int] = None
    api_max_rows: Optional[int] = None
    op_days: Optional[int] = None
    op_max_rows: Optional[int] = None


@router.get("/admin/log-retention")
async def admin_get_log_retention(admin: dict = Depends(require_admin)):
    """读取日志保留策略配置"""
    return {"success": True, "settings": get_logret_settings()}


@router.put("/admin/log-retention")
async def admin_set_log_retention(body: LogRetentionConfig, admin: dict = Depends(require_admin)):
    """更新日志保留策略配置（仅传入的字段生效）"""
    ensure_db()
    data = body.dict(exclude_unset=True)
    for k in _LOGRET_KEYS:
        if k in data and data[k] is not None:
            if k == "enabled":
                db.set_config("logret.enabled", "1" if data[k] else "0")
            else:
                db.set_config(f"logret.{k}", str(int(data[k])))
    tools.log_operation(admin["id"], "admin:set_log_retention", f"更新日志保留策略: {data}")
    return {"success": True, "settings": get_logret_settings()}


@router.post("/admin/log-retention/run")
async def admin_run_log_retention(admin: dict = Depends(require_admin)):
    """立即执行一次日志清理（手动触发，不受开关限制）"""
    res = run_log_retention()
    tools.log_operation(
        admin["id"], "admin:run_log_retention",
        f"手动清理日志: 接口 -{res['api_deleted']} 操作 -{res['op_deleted']}",
    )
    return {"success": True, **res}


# ============ 用户建议（非管理员提建议，管理员查看/回复/删除） ============

@router.post("/suggestions")
async def mu_create_suggestion(body: SuggestionCreate, user: dict = Depends(get_mu_user)):
    """提交一条建议（任何已登录用户），content 非空"""
    ensure_db()
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="建议内容不能为空")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="建议内容过长（最多 2000 字）")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_suggestions (user_id, username, content, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (user["id"], user.get("username", ""), content, datetime.now().isoformat()),
        )
        conn.commit()
        sug_id = cur.lastrowid
    finally:
        conn.close()
    tools.log_operation(user["id"], "suggestion:create", f"提交建议 #{sug_id}")
    return {"success": True, "id": sug_id}


@router.get("/suggestions")
async def mu_my_suggestions(user: dict = Depends(get_mu_user)):
    """查询自己的建议列表（含管理员回复），按时间倒序"""
    ensure_db()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, content, status, reply, replied_at, created_at "
            "FROM mu_suggestions WHERE user_id = ? ORDER BY id DESC LIMIT 200",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"success": True, "suggestions": [dict(r) for r in rows]}


@router.get("/admin/suggestions")
async def admin_list_suggestions(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    """管理员查询全部建议（可按状态筛选，分页）"""
    ensure_db()
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    where = "1=1"
    params: list = []
    if status:
        where += " AND s.status = ?"
        params.append(status)
    conn = db.get_conn()
    try:
        total = conn.execute(f"SELECT COUNT(*) c FROM mu_suggestions s WHERE {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT s.id, s.user_id, s.username, s.content, s.status, s.reply, s.replied_by, s.replied_at, s.created_at, u.display_name "
            f"FROM mu_suggestions s LEFT JOIN users u ON u.id = s.user_id "
            f"WHERE {where} ORDER BY s.id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()
    sugs = [dict(r) for r in rows]
    for s in sugs:
        s["display_name"] = s.get("display_name") or s.get("username") or f"用户#{s.get('user_id')}"
    return {"success": True, "suggestions": sugs, "total": total}


@router.put("/admin/suggestions/{sug_id}/reply")
async def admin_reply_suggestion(sug_id: int, body: SuggestionReply, admin: dict = Depends(require_admin)):
    """管理员回复建议（status 置为 replied，可多次回复覆盖）"""
    ensure_db()
    reply = (body.reply or "").strip()
    if not reply:
        raise HTTPException(status_code=400, detail="回复内容不能为空")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "UPDATE mu_suggestions SET reply = ?, status = 'replied', replied_by = ?, replied_at = ? "
            "WHERE id = ?",
            (reply, admin["id"], datetime.now().isoformat(), sug_id),
        )
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()
    if ok:
        tools.log_operation(admin["id"], "admin:reply_suggestion", f"回复建议 #{sug_id}")
    return {"success": ok}


@router.delete("/admin/suggestions/{sug_id}")
async def admin_delete_suggestion(sug_id: int, admin: dict = Depends(require_admin)):
    """管理员删除单条建议"""
    ensure_db()
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM mu_suggestions WHERE id = ?", (sug_id,))
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()
    if ok:
        tools.log_operation(admin["id"], "admin:delete_suggestion", f"删除建议 #{sug_id}")
    return {"success": ok}


@router.delete("/admin/suggestions")
async def admin_clear_suggestions(
    status: Optional[str] = None,
    admin: dict = Depends(require_admin),
):
    """管理员清空建议（可按状态，如 pending/replied）"""
    ensure_db()
    conn = db.get_conn()
    try:
        if status:
            cur = conn.execute("DELETE FROM mu_suggestions WHERE status = ?", (status,))
        else:
            cur = conn.execute("DELETE FROM mu_suggestions")
        conn.commit()
        deleted = cur.rowcount
    finally:
        conn.close()
    scope = f"{status} 状态" if status else "全部"
    tools.log_operation(admin["id"], "admin:clear_suggestions", f"清空{scope}建议（{deleted} 条）")
    return {"success": True, "deleted": deleted}


# ============ 通用：每用户限流（100 次/60s） ============

import time as _time
_rate_buckets: Dict[int, list] = {}


def check_user_rate(user: dict = Depends(get_mu_user)):
    uid = user["id"]
    now = _time.time()
    bucket = [t for t in _rate_buckets.get(uid, []) if now - t < 60]
    if len(bucket) >= 100:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    bucket.append(now)
    _rate_buckets[uid] = bucket
    return user


# ============ 聊天 ============

from lobster_mu import chat_service, session_store, upload_service, memory_store, script_service
from lobster_mu.chat_service import ChatMessageRequest, ChatStreamRequest
from fastapi import File, UploadFile


@router.get("/chat/models")
async def mu_chat_models(user: dict = Depends(get_mu_user)):
    return chat_service.get_chat_models()


@router.post("/chat/message")
async def mu_chat_message(body: ChatMessageRequest, request: Request, user: dict = Depends(check_user_rate)):
    ip = get_client_ip(request)
    tools.log_operation(user["id"], "chat", f"发送消息: {body.message[:100]}", ip=ip)
    return chat_service.chat_message_once(user["id"], body)


@router.post("/chat/stream")
async def mu_chat_stream(body: ChatStreamRequest, request: Request, user: dict = Depends(check_user_rate)):
    ip = get_client_ip(request)
    tools.log_operation(user["id"], "chat", f"发送消息: {body.message[:100]}", ip=ip)
    return chat_service.chat_stream_response(user["id"], body)


@router.get("/chat/sessions")
async def mu_chat_sessions(user: dict = Depends(get_mu_user)):
    return {"success": True, "sessions": session_store.list_sessions(user["id"])}


@router.get("/chat/session/{session_id}")
async def mu_chat_session_detail(session_id: str, user: dict = Depends(get_mu_user)):
    msgs = session_store.get_messages(user["id"], session_id)
    if msgs is None:
        return {"success": False, "error": "会话不存在"}
    return {"success": True, "session": {"id": session_id, "messages": msgs}}


@router.delete("/chat/session/{session_id}")
async def mu_chat_session_delete(session_id: str, user: dict = Depends(get_mu_user)):
    ok = session_store.delete_session(user["id"], session_id)
    return {"success": ok, "message": "会话已删除" if ok else "会话不存在"}


@router.post("/chat/session/{session_id}/star")
async def mu_chat_session_toggle_star(session_id: str, user: dict = Depends(get_mu_user)):
    """切换会话星标（置顶/取消）"""
    starred = session_store.toggle_star(user["id"], session_id)
    if starred is None:
        return {"success": False, "error": "会话不存在"}
    return {"success": True, "starred": starred}


@router.delete("/chat/sessions")
async def mu_chat_sessions_clear(user: dict = Depends(get_mu_user)):
    session_store.clear_sessions(user["id"])
    return {"success": True, "message": "所有会话已清空"}


# ============ 文件上传 ============

@router.post("/upload")
async def mu_upload(files: List[UploadFile] = File(...), user: dict = Depends(check_user_rate)):
    from lobster_mu import file_store
    results = []
    for file in files:
        try:
            content = await file.read()
            if len(content) > upload_service.MAX_UPLOAD_SIZE:
                results.append({"success": False, "filename": file.filename, "error": "文件超过10MB限制"})
                continue
            info = upload_service.save_upload(user["id"], file.filename, content)
            file_id = file_store.add(user["id"], file.filename, info["path"], info["size"], info["content"])
            results.append({
                "success": True,
                "file_id": file_id,
                "id": info["path"],
                "filename": file.filename,
                "size": info["size"],
                "content_preview": info["content"][:200] if info["content"] else "",
            })
        except Exception as e:
            results.append({"success": False, "filename": file.filename, "error": str(e)})
    return {"results": results}


@router.get("/files")
async def mu_files_list(user: dict = Depends(check_user_rate)):
    from lobster_mu import file_store
    return {"success": True, "files": file_store.list_files(user["id"])}


@router.get("/files/{file_id}")
async def mu_files_get(file_id: int, user: dict = Depends(check_user_rate)):
    from lobster_mu import file_store
    f = file_store.get(user["id"], file_id)
    if not f:
        return {"success": False, "error": "文件不存在"}
    return {"success": True, "file": {
        "id": f["id"], "filename": f["filename"], "size": f["file_size"],
        "content": f["content"], "created_at": f["created_at"],
    }}


@router.delete("/files/{file_id}")
async def mu_files_delete(file_id: int, user: dict = Depends(check_user_rate)):
    from lobster_mu import file_store
    ok = file_store.delete(user["id"], file_id)
    return {"success": ok, "error": None if ok else "文件不存在"}


@router.get("/files/{file_id}/raw")
async def mu_files_raw(file_id: int, download: int = 0, user: dict = Depends(check_user_rate)):
    """流式返回原始文件：inline 用于预览（如 PDF 内嵌），download=1 触发下载。"""
    import mimetypes
    from fastapi.responses import FileResponse
    from lobster_mu import file_store
    f = file_store.get(user["id"], file_id)
    if not f or not f.get("stored_path") or not os.path.exists(f["stored_path"]):
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type, _ = mimetypes.guess_type(f["filename"])
    return FileResponse(
        f["stored_path"],
        media_type=media_type or "application/octet-stream",
        filename=f["filename"],
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/files/{file_id}/to-knowledge")
async def mu_files_to_knowledge(file_id: int, user: dict = Depends(check_user_rate)):
    """把「我的文件」库中的文件加入知识库：重新提取文本（带乱码检测）后入库"""
    ensure_db()
    import shutil
    from lobster_mu import file_store
    from lobster_mu.paths import uploads_dir, gen_filename
    from lobster_mu.upload_service import extract_text

    f = file_store.get(user["id"], file_id)
    if not f:
        return {"success": False, "error": "文件不存在"}

    src_path = f.get("stored_path") or ""
    try:
        if src_path and os.path.exists(src_path):
            # 有原始文件：复制到知识库 uploads 目录并从原始文件重新提取（PDF 等更准确）
            ext = os.path.splitext(f["filename"] or "")[1][:16].lower()
            dst_path = os.path.join(uploads_dir(user["id"]), gen_filename(f["filename"]))

            def _copy_and_extract():
                shutil.copyfile(src_path, dst_path)
                return extract_text(dst_path, ext)

            text_content = await asyncio.to_thread(_copy_and_extract)
            stored_name = os.path.basename(dst_path)
            file_size = f["file_size"] or os.path.getsize(dst_path)
        else:
            # 无原始文件（仅存了提取文本）：直接用已存内容入库
            text_content = f.get("content") or ""
            stored_name = ""
            file_size = f["file_size"] or len(text_content.encode("utf-8", "ignore"))

        result = await asyncio.to_thread(
            knowledge_store.add_document,
            user["id"], f["filename"], file_size, text_content, stored_name,
        )
        return {"success": True, "doc_id": result["doc_id"], "filename": f["filename"],
                "chunk_count": result["chunk_count"], "shared": result.get("shared", False)}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/upload/text")
async def mu_upload_text(file: UploadFile = File(...), user: dict = Depends(check_user_rate)):
    try:
        content = await file.read()
        if len(content) > upload_service.MAX_UPLOAD_SIZE:
            return {"success": False, "error": "文件超过10MB限制"}
        return upload_service.save_upload_text(user["id"], file.filename, content)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ 记忆 ============

class MemoryAddRequest(BaseModel):
    type: str = "short_term"
    content: str
    session_id: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str
    type: Optional[str] = None
    limit: int = 20


@router.get("/memory/list")
async def mu_memory_list(type: Optional[str] = None, limit: int = 100, user: dict = Depends(get_mu_user)):
    return {"success": True, "memories": memory_store.list_memories(user["id"], type, limit)}


@router.post("/memory/add")
async def mu_memory_add(body: MemoryAddRequest, user: dict = Depends(get_mu_user)):
    try:
        mid = memory_store.add_memory(user["id"], body.type, body.content, body.session_id)
        return {"success": True, "id": mid}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/memory/{memory_id}")
async def mu_memory_delete(memory_id: int, user: dict = Depends(get_mu_user)):
    ok = memory_store.delete_memory(user["id"], memory_id)
    return {"success": ok, "message": "已删除" if ok else "记忆不存在"}


@router.post("/memory/search")
async def mu_memory_search(body: MemorySearchRequest, user: dict = Depends(get_mu_user)):
    return {"success": True, "results": memory_store.search_memories(user["id"], body.query, body.type, body.limit)}


@router.delete("/memory/clear")
async def mu_memory_clear(type: Optional[str] = None, user: dict = Depends(get_mu_user)):
    n = memory_store.clear_memories(user["id"], type)
    return {"success": True, "deleted": n}


# ============ 脚本系统 ============

class ScriptCreateRequest(BaseModel):
    name: Optional[str] = None
    description: str = ""
    code: str


class ScriptUpdateRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None


class ScriptExecRequest(BaseModel):
    script_id: Optional[int] = None
    code: Optional[str] = None
    timeout: int = 60


class DependencyCheckRequest(BaseModel):
    code: str


class DependencyInstallRequest(BaseModel):
    package: str


@router.post("/script/create")
async def mu_script_create(body: ScriptCreateRequest, user: dict = Depends(check_user_rate)):
    ensure_db()
    name = body.name or f"script_{int(_time.time())}"
    sid = script_service.create_script(user["id"], name, body.code, body.description, is_approved=False)
    syntax = script_service.check_script_syntax(body.code)
    return {"success": True, "script_id": sid, "name": name, "syntax": syntax}


@router.get("/script/list")
async def mu_script_list(user: dict = Depends(get_mu_user)):
    return {"success": True, "scripts": script_service.list_scripts(user["id"])}


@router.get("/script/installation-status")
async def mu_script_install_status(user: dict = Depends(get_mu_user)):
    return script_service.get_installation_status(user["id"])


@router.get("/script/{script_id}")
async def mu_script_detail(script_id: int, user: dict = Depends(get_mu_user)):
    s = script_service.get_script(user["id"], script_id)
    if not s:
        return {"success": False, "error": "脚本不存在"}
    return {"success": True, "script": s}


@router.put("/script/{script_id}")
async def mu_script_update(script_id: int, body: ScriptUpdateRequest, user: dict = Depends(get_mu_user)):
    ok = script_service.update_script(user["id"], script_id, body.name, body.code, body.description)
    return {"success": ok, "message": "已更新" if ok else "脚本不存在"}


@router.delete("/script/{script_id}")
async def mu_script_delete(script_id: int, user: dict = Depends(get_mu_user)):
    ok = script_service.delete_script(user["id"], script_id)
    return {"success": ok, "message": "已删除" if ok else "脚本不存在"}


@router.post("/script/{script_id}/approve")
async def mu_script_approve(script_id: int, user: dict = Depends(get_mu_user)):
    ok = script_service.approve_script(user["id"], script_id)
    return {"success": ok, "message": "已批准" if ok else "脚本不存在"}


@router.post("/script/{script_id}/revoke")
async def mu_script_revoke(script_id: int, user: dict = Depends(get_mu_user)):
    ok = script_service.revoke_script(user["id"], script_id)
    return {"success": ok, "message": "已撤销" if ok else "脚本不存在"}


@router.post("/script/check-dependencies")
async def mu_script_check_deps(body: DependencyCheckRequest, user: dict = Depends(get_mu_user)):
    missing = script_service.detect_missing_dependencies(body.code)
    return {"success": True, "missing": missing}


@router.post("/script/install-dependency")
async def mu_script_install_dep(body: DependencyInstallRequest, user: dict = Depends(check_user_rate)):
    result = script_service.install_dependency_sync(user["id"], body.package)
    return result


@router.post("/script/install-dependency-async")
async def mu_script_install_dep_async(body: DependencyInstallRequest, user: dict = Depends(get_mu_user)):
    return script_service.install_dependency_async(user["id"], body.package)


@router.get("/script/files/download/{file_name}")
async def mu_script_file_download(file_name: str, download: int = 0, user: dict = Depends(get_mu_user)):
    from fastapi.responses import FileResponse
    try:
        path = script_service.get_generated_file_path(user["id"], file_name)
    except ValueError:
        raise HTTPException(status_code=403, detail="无权访问该文件")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    # 默认 inline（浏览器可直接预览/打开）；?download=1 时强制下载
    if download:
        return FileResponse(path, filename=os.path.basename(path))
    return FileResponse(path)


@router.get("/script/files/list")
async def mu_script_files_list(user: dict = Depends(get_mu_user)):
    return {"success": True, "files": script_service.list_generated_files(user["id"])}


@router.post("/script/execute")
async def mu_script_execute(body: ScriptExecRequest, user: dict = Depends(check_user_rate)):
    ensure_db()
    if body.code:
        result = script_service.execute_python_script(user["id"], body.code, timeout=body.timeout)
        return result
    if body.script_id:
        s = script_service.get_script(user["id"], body.script_id)
        if not s:
            return {"success": False, "error": "脚本不存在"}
        if not s["is_approved"]:
            return {"success": False, "error": "脚本未批准，请先批准后执行"}
        return script_service.execute_python_script(user["id"], s["code"], timeout=body.timeout)
    return {"success": False, "error": "缺少 script_id 或 code"}


@router.post("/script/generate-pdf")
async def mu_script_generate_pdf(body: dict, user: dict = Depends(check_user_rate)):
    content = (body or {}).get("content", "") or (body or {}).get("text", "")
    if not content:
        raise HTTPException(status_code=400, detail="缺少 content 内容")
    from lobster_mu import tools
    result_str = tools._tool_generate_pdf(content, user["id"])
    return {"success": "❌" not in result_str, "message": result_str}


# ============ 技能（Skill）多用户 ============

@router.get("/skill/list")
async def mu_skill_list(user: dict = Depends(get_mu_user)):
    from lobster_mu import skill_store
    return {"success": True, "skills": skill_store.list_skills(user["id"])}


@router.post("/skill")
async def mu_skill_create(body: dict, user: dict = Depends(get_mu_user)):
    from lobster_mu import skill_store
    return skill_store.add(user["id"], body or {})


def _skill_import_preview(parsed: dict) -> dict:
    return {
        "name": parsed.get("name", ""),
        "description": parsed.get("description", ""),
        "body_preview": (parsed.get("body", "") or "")[:300],
        "scripts": list((parsed.get("scripts") or {}).keys()),
        "references": list((parsed.get("references") or {}).keys()),
        "source": "skillmd",
    }


def _is_safe_url(url: str) -> tuple[bool, str]:
    """URL 安全校验：仅 http/https，且主机不是本地/私网地址（防 SSRF）。"""
    from urllib.parse import urlparse
    import ipaddress
    try:
        pu = urlparse(url)
    except Exception:
        return False, "URL 解析失败"
    if pu.scheme not in ("http", "https"):
        return False, "仅允许 http/https 链接"
    host = (pu.hostname or "").lower()
    if not host:
        return False, "URL 缺少主机"
    if host in ("localhost",) or host.endswith(".local"):
        return False, "禁止访问本地地址"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, "禁止访问内网地址"
    except ValueError:
        pass  # 域名，放行（由 DNS/出站策略兜底）
    return True, ""


@router.post("/skill/import")
async def mu_skill_import(body: dict, user: dict = Depends(get_mu_user)):
    """粘贴 SKILL.md 内容导入。confirm=False 仅返回预览（不写入）。"""
    from lobster_mu import skill_importer
    content = (body or {}).get("content") or ""
    is_public = bool((body or {}).get("is_public"))
    confirm = bool((body or {}).get("confirm", True))
    is_admin = user.get("role") == "admin"
    if not content.strip():
        return {"success": False, "error": "内容为空"}
    parsed = skill_importer.parse_skill_md(content)
    if parsed.get("error"):
        return {"success": False, "error": parsed["error"]}
    if not confirm:
        return {"success": True, "preview": _skill_import_preview(parsed), "parsed": parsed}
    return skill_importer.import_skill_package(user["id"], parsed, is_public=is_public, is_admin=is_admin)


@router.post("/skill/import/upload")
async def mu_skill_import_upload(
    file: UploadFile = File(...),
    is_public: bool = Form(False),
    confirm: bool = Form(True),
    user: dict = Depends(get_mu_user),
):
    """上传 .md 或 .zip 技能包导入。confirm=False 仅预览。"""
    from lobster_mu import skill_importer
    is_admin = user.get("role") == "admin"
    try:
        data = await file.read()
    except Exception as e:
        return {"success": False, "error": f"读取文件失败: {e}"}
    parsed = skill_importer.parse_bytes(data, filename=file.filename or "")
    if parsed.get("error"):
        return {"success": False, "error": parsed["error"]}
    if not confirm:
        return {"success": True, "preview": _skill_import_preview(parsed), "parsed": parsed}
    return skill_importer.import_skill_package(user["id"], parsed, is_public=is_public, is_admin=is_admin)


def _github_zip_url(owner: str, repo: str, branch: str) -> str:
    return f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"


def _expand_skill_url_candidates(url: str) -> list:
    """GitHub 页面地址自动补全为可下载的技能包地址（按优先级排序的候选列表）。

    - 仓库主页      github.com/o/r            → 默认分支 zip（API 解析失败则 main/master 依次尝试）
    - 分支页        github.com/o/r/tree/b     → 该分支 zip
    - 文件页        github.com/o/r/blob/b/p   → raw 文件地址
    - 其余（raw/codeload/直链/非 GitHub）→ 原样返回
    """
    from urllib.parse import urlparse
    try:
        pu = urlparse(url)
    except Exception:
        return [url]
    host = (pu.hostname or "").lower()
    path = pu.path.strip("/")
    if host != "github.com" or not path:
        return [url]
    parts = path.split("/")
    if len(parts) < 2:
        return [url]
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return [url]
    # 仓库主页（含 .git 后缀）：解析默认分支 → zip 归档
    if len(parts) == 2:
        cands = []
        try:
            import httpx
            with httpx.Client(timeout=8, follow_redirects=True) as c:
                r = c.get(f"https://api.github.com/repos/{owner}/{repo}",
                          headers={"Accept": "application/vnd.github+json"})
                if r.status_code == 200:
                    branch = (r.json() or {}).get("default_branch")
                    if branch:
                        cands.append(_github_zip_url(owner, repo, branch))
        except Exception:
            pass
        for b in ("main", "master"):
            u = _github_zip_url(owner, repo, b)
            if u not in cands:
                cands.append(u)
        return cands
    # 分支/目录页：直接用该分支打 zip（导入器会在包内定位 SKILL.md）
    if parts[2] == "tree" and len(parts) >= 4:
        return [_github_zip_url(owner, repo, parts[3])]
    # 文件页：转 raw 直链
    if parts[2] == "blob" and len(parts) >= 5:
        fpath = "/".join(parts[4:])
        return [f"https://raw.githubusercontent.com/{owner}/{repo}/{parts[3]}/{fpath}"]
    return [url]


@router.post("/skill/import/url")
async def mu_skill_import_url(body: dict, user: dict = Depends(get_mu_user)):
    """从 URL 拉取 SKILL.md / zip 导入；GitHub 仓库/分支/文件页地址自动补全。confirm=False 仅预览。"""
    from lobster_mu import skill_importer
    url = ((body or {}).get("url") or "").strip()
    is_public = bool((body or {}).get("is_public"))
    confirm = bool((body or {}).get("confirm", True))
    is_admin = user.get("role") == "admin"

    candidates = _expand_skill_url_candidates(url)
    data = None
    used_url = url
    last_err = ""
    import httpx
    for cand in candidates:
        ok, msg = _is_safe_url(cand)
        if not ok:
            last_err = msg
            continue
        try:
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                resp = client.get(cand)
                resp.raise_for_status()
                data = resp.content
                used_url = cand
                break
        except Exception as e:
            last_err = f"{cand} → {e}"
            continue
    if data is None:
        return {"success": False, "error": f"拉取失败: {last_err or '无可用地址'}"}

    # 按扩展名或内容判定
    from urllib.parse import urlparse
    path = urlparse(used_url).path.lower()
    if not path.endswith(".zip") and skill_importer._is_zip_bytes(data) is False and path.endswith((".md", ".markdown")):
        parsed = skill_importer.parse_skill_md(data.decode("utf-8", errors="replace"))
    else:
        parsed = skill_importer.parse_bytes(data, filename=path)
    if parsed.get("error"):
        return {"success": False, "error": parsed["error"]}
    if not confirm:
        return {"success": True, "preview": _skill_import_preview(parsed), "parsed": parsed,
                "resolved_url": used_url}
    result = skill_importer.import_skill_package(user["id"], parsed, is_public=is_public, is_admin=is_admin)
    if isinstance(result, dict):
        result["resolved_url"] = used_url
    return result


@router.get("/skill/{skill_id}")
async def mu_skill_detail(skill_id: str, user: dict = Depends(get_mu_user)):
    from lobster_mu import skill_store
    s = skill_store.get(user["id"], skill_id)
    if not s:
        return {"success": False, "error": "技能不存在或无权访问"}
    return {"success": True, "skill": s}


@router.put("/skill/{skill_id}")
async def mu_skill_update(skill_id: str, body: dict, user: dict = Depends(get_mu_user)):
    from lobster_mu import skill_store
    return skill_store.update(user["id"], skill_id, body or {})


@router.delete("/skill/{skill_id}")
async def mu_skill_delete(skill_id: str, user: dict = Depends(get_mu_user)):
    from lobster_mu import skill_store
    return skill_store.delete(user["id"], skill_id)


@router.post("/skill/{skill_id}/enable")
async def mu_skill_enable(skill_id: str, user: dict = Depends(get_mu_user)):
    from lobster_mu import skill_store
    return skill_store.set_enabled(user["id"], skill_id, True)


@router.post("/skill/{skill_id}/disable")
async def mu_skill_disable(skill_id: str, user: dict = Depends(get_mu_user)):
    from lobster_mu import skill_store
    return skill_store.set_enabled(user["id"], skill_id, False)


@router.post("/skill/{skill_id}/execute")
def mu_skill_execute(skill_id: str, body: dict, user: dict = Depends(check_user_rate)):
    # 同步阻塞的 LLM 调用必须用 def（FastAPI 放入线程池），用 async def 会阻塞整个事件循环
    from lobster_mu import skill_store
    return skill_store.execute(user["id"], skill_id, (body or {}).get("params") or {})


# ---- 管理员：公共技能管理 ----

@router.get("/admin/skill/list")
async def admin_skill_list(admin: dict = Depends(require_admin)):
    from lobster_mu import skill_store
    return {"success": True, "skills": skill_store.list_all()}


@router.post("/admin/skill")
async def admin_skill_create(body: dict, admin: dict = Depends(require_admin)):
    from lobster_mu import skill_store
    return skill_store.add(0, body or {}, is_public=True, is_admin=True)


@router.put("/admin/skill/{skill_id}")
async def admin_skill_update(skill_id: str, body: dict, admin: dict = Depends(require_admin)):
    from lobster_mu import skill_store
    return skill_store.update(0, skill_id, body or {}, is_admin=True)


@router.delete("/admin/skill/{skill_id}")
async def admin_skill_delete(skill_id: str, admin: dict = Depends(require_admin)):
    from lobster_mu import skill_store
    return skill_store.delete(0, skill_id, is_admin=True)


@router.post("/admin/skill/{skill_id}/public")
async def admin_skill_set_public(skill_id: str, body: dict, admin: dict = Depends(require_admin)):
    from lobster_mu import skill_store
    return skill_store.set_public(skill_id, bool((body or {}).get("is_public")), is_admin=True)


@router.post("/admin/skill/{skill_id}/enable")
async def admin_skill_enable(skill_id: str, admin: dict = Depends(require_admin)):
    from lobster_mu import skill_store
    return skill_store.set_enabled(0, skill_id, True, is_admin=True)


@router.post("/admin/skill/{skill_id}/disable")
async def admin_skill_disable(skill_id: str, admin: dict = Depends(require_admin)):
    from lobster_mu import skill_store
    return skill_store.set_enabled(0, skill_id, False, is_admin=True)


# ============ 工具端点（per-user 路径白名单） ============

class ExecCommandRequest(BaseModel):
    command: str
    timeout: int = 30


class FileReadRequest(BaseModel):
    path: str


class FileWriteRequest(BaseModel):
    path: str
    content: str


class DirListRequest(BaseModel):
    path: str = "."


class HttpRequest(BaseModel):
    url: str
    headers: Optional[Dict[str, str]] = None
    data: Optional[Dict[str, Any]] = None


class BrowseRequest(BaseModel):
    url: str
    timeout: int = 30


class EditFileRequest(BaseModel):
    path: str
    old_text: str
    new_text: str


class ApplyPatchRequest(BaseModel):
    patches: List[Dict[str, Any]]


class WebSearchRequest(BaseModel):
    query: str
    count: int = 5


@router.post("/exec")
async def mu_exec(body: ExecCommandRequest, user: dict = Depends(check_user_rate)):
    """HTTP 命令执行端点（spec §2.3 T5）：
    复用 exec_cmd 的白名单+黑名单校验（修复现状 /exec 无白名单缺口），
    再经沙箱执行器取结构化结果（user 角色走 Docker 沙箱，admin 直通）。"""
    import asyncio
    from lobster_mu import tools
    uid = user["id"]
    # 1. 白名单+黑名单校验（与 Agent exec 工具一致）
    if not body.command or not body.command.strip():
        return {"success": False, "error": "命令不能为空"}
    cmd_lower = body.command.strip().lower().split()[0]
    if cmd_lower in tools.DANGEROUS_COMMANDS:
        tools.log_operation(uid, "exec", body.command[:100], success=False, error="危险命令")
        return {"success": False, "error": f"危险命令禁止执行: {cmd_lower}"}
    if cmd_lower not in tools.ALLOWED_COMMANDS:
        tools.log_operation(uid, "exec", body.command[:100], success=False, error="命令不在允许列表")
        return {"success": False, "error": f"命令不在允许列表中: {cmd_lower}"}
    if not tools.is_command_safe(body.command):
        tools.log_operation(uid, "exec", body.command[:100], success=False, error="危险命令")
        return {"success": False, "error": "危险命令禁止执行"}
    # 2. 沙箱执行（同步 exec_shell 放线程池避免阻塞事件循环）
    loop = asyncio.get_event_loop()
    sr = await loop.run_in_executor(
        None, lambda: tools.execute_shell_command(body.command, body.timeout, uid, raw=True)
    )
    tools.log_operation(uid, "exec", body.command[:100], success=sr.success,
                        error=sr.error or "")
    d = {"success": sr.success, "stdout": sr.stdout, "stderr": sr.stderr,
         "return_code": sr.return_code}
    if sr.error:
        d["error"] = sr.error
    return d


@router.post("/read_file")
async def mu_read_file(body: FileReadRequest, user: dict = Depends(get_mu_user)):
    from lobster_mu import tools
    return {"success": True, "content": tools.read_file(body.path, user["id"])}


@router.post("/write_file")
async def mu_write_file(body: FileWriteRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import tools
    return {"success": True, "message": tools.write_file(body.path, body.content, user["id"])}


@router.post("/list_dir")
async def mu_list_dir(body: DirListRequest, user: dict = Depends(get_mu_user)):
    from lobster_mu import tools
    return {"success": True, "content": tools.list_dir(body.path, user["id"])}


@router.post("/http_get")
async def mu_http_get(body: HttpRequest, user: dict = Depends(get_mu_user)):
    from lobster_mu import tools
    return {"success": True, "content": tools.http_get(body.url, body.headers)}


@router.post("/http_post")
async def mu_http_post(body: HttpRequest, user: dict = Depends(get_mu_user)):
    from lobster_mu import tools
    return {"success": True, "content": tools.http_post(body.url, body.headers, body.data)}


@router.post("/browse")
async def mu_browse(body: BrowseRequest, user: dict = Depends(get_mu_user)):
    from lobster_mu import tools
    return {"success": True, "content": tools.browse(body.url, body.timeout)}


@router.post("/screenshot")
async def mu_screenshot(body: BrowseRequest, user: dict = Depends(get_mu_user)):
    from lobster_mu import tools
    return {"success": True, "content": tools.screenshot(body.url, body.timeout, user["id"])}


@router.post("/edit")
async def mu_edit_file(body: EditFileRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import tools
    return {"success": True, "message": tools.edit_file(body.path, body.old_text, body.new_text, user["id"])}


@router.post("/apply_patch")
async def mu_apply_patch(body: ApplyPatchRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import tools
    return {"success": True, "message": tools.apply_patch(body.patches, user["id"])}


@router.post("/web_search")
async def mu_web_search(body: WebSearchRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import tools
    return {"success": True, "content": tools.web_search(body.query, body.count)}


# ============ 环境感知 / 历史 / 安全 ============

@router.get("/environment/snapshot")
async def mu_environment_snapshot(user: dict = Depends(get_mu_user)):
    from web.routes.lobster_claw import get_environment_snapshot
    return get_environment_snapshot()


def _log_op(user_id: int, operation: str, detail: str, success: bool = True, ip: str = ""):
    from lobster_mu import tools
    tools.log_operation(user_id, operation, detail, success=success, ip=ip)


@router.get("/history")
async def mu_history(limit: int = 50, user: dict = Depends(get_mu_user)):
    from lobster_mu.db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, operation, detail, success, ip, created_at FROM mu_operation_logs"
            " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user["id"], limit),
        ).fetchall()
    finally:
        conn.close()
    return {"success": True, "history": [dict(r) for r in rows]}


@router.delete("/history/{record_id}")
async def mu_history_delete(record_id: int, user: dict = Depends(get_mu_user)):
    from lobster_mu.db import get_conn
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM mu_operation_logs WHERE id = ? AND user_id = ?", (record_id, user["id"]))
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()
    return {"success": ok}


@router.delete("/history")
async def mu_history_clear(user: dict = Depends(get_mu_user)):
    from lobster_mu.db import get_conn
    conn = get_conn()
    try:
        conn.execute("DELETE FROM mu_operation_logs WHERE user_id = ?", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    return {"success": True}


@router.get("/security/logs")
async def mu_security_logs(limit: int = 100, user: dict = Depends(get_mu_user)):
    from lobster_mu.db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_operation_logs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user["id"], limit),
        ).fetchall()
    finally:
        conn.close()
    return {"success": True, "logs": [dict(r) for r in rows]}


@router.get("/security/stats")
async def mu_security_stats(user: dict = Depends(get_mu_user)):
    from lobster_mu.db import get_conn
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) c FROM mu_operation_logs WHERE user_id = ?", (user["id"],)).fetchone()["c"]
        failed = conn.execute(
            "SELECT COUNT(*) c FROM mu_operation_logs WHERE user_id = ? AND success = 0", (user["id"],)
        ).fetchone()["c"]
    finally:
        conn.close()
    return {"success": True, "stats": {"total_operations": total, "failed_operations": failed}}


@router.get("/security/allowed_paths")
async def mu_security_allowed_paths(user: dict = Depends(get_mu_user)):
    from lobster_mu import paths
    return {"success": True, "allowed_paths": [
        paths.mu_files_dir(user["id"]), paths.uploads_dir(user["id"]), paths.files_dir(user["id"]),
    ], "read_only_paths": [paths.USER_READ_ONLY_EXTRA]}


@router.get("/security/permission_levels")
async def mu_security_permission_levels(user: dict = Depends(get_mu_user)):
    return {"success": True, "permission_levels": {
        "admin": ["全部工具与管理端"],
        "user": ["read_file", "list_dir", "exec", "http_get", "http_post", "browse",
                 "screenshot", "web_search", "chat", "script", "memory", "cron", "knowledge"],
    }}


# ============ 定时任务 Cron（user_id 隔离，独立于旧调度器 cron.db） ============

from cron.cron_scheduler import CronParser
from lobster_mu import cron_store, agent_store, knowledge_store
from lobster_mu.cron_runner import mu_scheduler


class CronMuRequest(BaseModel):
    name: str
    task_type: str
    content: str
    schedule: Optional[str] = None
    run_at: Optional[str] = None
    enabled: bool = True
    timeout: int = 300


@router.post("/cron/add")
async def mu_cron_add(body: CronMuRequest, user: dict = Depends(check_user_rate)):
    ensure_db()
    try:
        if body.task_type not in ["ai", "command"]:
            return {"success": False, "error": "任务类型必须是 'ai' 或 'command'"}
        if not body.schedule and not body.run_at:
            return {"success": False, "error": "必须指定 schedule（cron表达式）或 run_at（执行时间）"}
        if body.schedule:
            try:
                CronParser.parse(body.schedule)
            except ValueError as e:
                return {"success": False, "error": f"Cron表达式格式错误: {e}"}

        from lobster_mu import tools
        if body.task_type == "command" and not tools.is_command_safe(body.content):
            return {"success": False, "error": "安全警告：该命令不在白名单中"}

        task = cron_store.create(
            user["id"], body.name, body.task_type, body.content,
            schedule=body.schedule, run_at=body.run_at,
            enabled=body.enabled, timeout=body.timeout,
        )
        if body.schedule and task["enabled"]:
            next_run = CronParser.get_next_run(body.schedule)
            cron_store.set_next_run(user["id"], task["id"], next_run.isoformat())
            task = cron_store.get_task(user["id"], task["id"])
        return {"success": True, "message": "定时任务创建成功", "task": task}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/cron/list")
async def mu_cron_list(enabled: Optional[bool] = None, user: dict = Depends(get_mu_user)):
    return {"success": True, "tasks": cron_store.list_tasks(user["id"], enabled=enabled)}


@router.get("/cron/runs/recent")
async def mu_cron_recent_runs(since_id: int = 0, limit: int = 50, only_finished: bool = True,
                              user: dict = Depends(get_mu_user)):
    """跨任务获取当前用户最近的运行记录（增量拉取）"""
    runs = cron_store.recent_runs(user["id"], since_id=since_id, limit=limit,
                                  only_finished=only_finished)
    return {"success": True, "runs": runs}


@router.get("/cron/{task_id}")
async def mu_cron_get(task_id: int, user: dict = Depends(get_mu_user)):
    task = cron_store.get_task(user["id"], task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    return {"success": True, "task": task}


@router.put("/cron/{task_id}")
async def mu_cron_update(task_id: int, body: CronMuRequest, user: dict = Depends(get_mu_user)):
    try:
        task = cron_store.get_task(user["id"], task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        if body.task_type not in ["ai", "command"]:
            return {"success": False, "error": "任务类型必须是 'ai' 或 'command'"}
        if body.schedule:
            try:
                CronParser.parse(body.schedule)
            except ValueError as e:
                return {"success": False, "error": f"Cron表达式格式错误: {e}"}

        from lobster_mu import tools
        if body.task_type == "command" and not tools.is_command_safe(body.content):
            return {"success": False, "error": "安全警告：该命令不在白名单中"}

        cron_store.update_task(
            user["id"], task_id,
            name=body.name, task_type=body.task_type, content=body.content,
            schedule=body.schedule, run_at=body.run_at,
            enabled=1 if body.enabled else 0, timeout=body.timeout,
        )
        if body.schedule and body.enabled:
            next_run = CronParser.get_next_run(body.schedule)
            cron_store.set_next_run(user["id"], task_id, next_run.isoformat())
        task = cron_store.get_task(user["id"], task_id)
        return {"success": True, "message": "任务已更新", "task": task}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/cron/{task_id}")
async def mu_cron_delete(task_id: int, user: dict = Depends(get_mu_user)):
    task = cron_store.get_task(user["id"], task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    cron_store.delete_task(user["id"], task_id)
    return {"success": True, "message": f"任务已删除: {task['name']}"}


@router.post("/cron/toggle/{task_id}")
async def mu_cron_toggle(task_id: int, user: dict = Depends(get_mu_user)):
    task = cron_store.toggle_task(user["id"], task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    if task["enabled"] and task["schedule"]:
        next_run = CronParser.get_next_run(task["schedule"])
        cron_store.set_next_run(user["id"], task_id, next_run.isoformat())
        task = cron_store.get_task(user["id"], task_id)
    return {"success": True,
            "message": f"任务状态已更新: {'启用' if task['enabled'] else '禁用'}", "task": task}


@router.get("/cron/{task_id}/runs")
async def mu_cron_runs(task_id: int, limit: int = 50, user: dict = Depends(get_mu_user)):
    task = cron_store.get_task(user["id"], task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    return {"success": True, "runs": cron_store.get_runs(user["id"], task_id, limit=limit)}


@router.post("/cron/{task_id}/run-now")
async def mu_cron_run_now(task_id: int, user: dict = Depends(get_mu_user)):
    task = cron_store.get_task(user["id"], task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    if not task["enabled"]:
        return {"success": False, "error": "任务已禁用"}
    mu_scheduler.run_now(user["id"], task)
    return {"success": True, "message": "任务已触发执行"}


# ============ Agent 系统（user_id 隔离，落库替代原内存全局列表） ============

class MuAgentCreateRequest(BaseModel):
    """Agent 创建/更新请求（personality=人设，model_name=绑定模型名，avatar/tone=人格化，
    capabilities=能力清单：web_search 联网搜索 / mcp MCP外部工具）"""
    name: str
    personality: Optional[str] = "default"
    permissions: Optional[List[str]] = None
    memory_size: int = 100
    model_name: Optional[str] = None
    avatar: Optional[str] = None
    tone: Optional[str] = None
    capabilities: Optional[List[str]] = None


@router.post("/agent/create")
async def mu_agent_create(body: MuAgentCreateRequest, user: dict = Depends(get_mu_user)):
    ensure_db()
    try:
        agent = agent_store.create_agent(
            user["id"], body.name,
            role_description=body.personality or "",
            model_name=body.model_name,
            model_type="text",
            avatar=body.avatar or "🤖",
            tone=body.tone or "",
            capabilities=body.capabilities or [],
        )
        return {"success": True, "message": "Agent创建成功", "agent": agent}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/agent/list")
async def mu_agent_list(user: dict = Depends(get_mu_user)):
    return {"success": True, "agents": agent_store.list_agents(user["id"])}


@router.get("/agent/{agent_id}")
async def mu_agent_get(agent_id: int, user: dict = Depends(get_mu_user)):
    agent = agent_store.get_agent(user["id"], agent_id)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "agent": agent}


@router.put("/agent/{agent_id}")
async def mu_agent_update(agent_id: int, body: MuAgentCreateRequest,
                          user: dict = Depends(get_mu_user)):
    agent = agent_store.update_agent(user["id"], agent_id,
                                     name=body.name,
                                     role_description=body.personality or "",
                                     model_name=body.model_name,
                                     avatar=body.avatar,
                                     tone=body.tone,
                                     capabilities=body.capabilities)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "message": "Agent更新成功", "agent": agent}


@router.delete("/agent/{agent_id}")
async def mu_agent_delete(agent_id: int, user: dict = Depends(get_mu_user)):
    agent = agent_store.get_agent(user["id"], agent_id)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    agent_store.delete_agent(user["id"], agent_id)
    return {"success": True, "message": f"Agent已删除: {agent['name']}"}


@router.post("/agent/{agent_id}/add_memory")
async def mu_agent_add_memory(agent_id: int, request: Dict[str, Any],
                              user: dict = Depends(get_mu_user)):
    content = (request or {}).get("content", "")
    mid = agent_store.add_memory(user["id"], agent_id, content)
    if mid is None:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "message": "记忆已添加", "id": mid}


@router.get("/agent/{agent_id}/memory")
async def mu_agent_get_memory(agent_id: int, user: dict = Depends(get_mu_user)):
    memories = agent_store.list_memories(user["id"], agent_id)
    if memories is None:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "memory": memories}


@router.delete("/agent/{agent_id}/memory/{memory_id}")
async def mu_agent_delete_memory(agent_id: int, memory_id: int,
                                 user: dict = Depends(get_mu_user)):
    ok = agent_store.delete_memory(user["id"], agent_id, memory_id)
    return {"success": ok, "message": "记忆已删除" if ok else "记忆不存在"}


# ============ Agent 长期计划 ============

from lobster_mu import plan_store


class MuPlanCreateRequest(BaseModel):
    title: str
    steps: List[str] = []


class MuPlanToggleRequest(BaseModel):
    step_index: int
    done: bool


class MuPlanStatusRequest(BaseModel):
    status: str


@router.get("/agent/{agent_id}/plans")
async def mu_agent_plans(agent_id: int, user: dict = Depends(get_mu_user)):
    plans = plan_store.list_plans(user["id"], agent_id)
    if plans is None:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "plans": plans}


@router.post("/agent/{agent_id}/plans")
async def mu_agent_plan_create(agent_id: int, body: MuPlanCreateRequest,
                               user: dict = Depends(get_mu_user)):
    try:
        plan = plan_store.create_plan(user["id"], agent_id, body.title, body.steps)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    if plan is None:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "message": "计划已创建", "plan": plan}


@router.put("/agent/{agent_id}/plans/{plan_id}/toggle")
async def mu_agent_plan_toggle(agent_id: int, plan_id: int, body: MuPlanToggleRequest,
                               user: dict = Depends(get_mu_user)):
    try:
        plan = plan_store.toggle_step(user["id"], plan_id, body.step_index, body.done)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    if plan is None:
        return {"success": False, "error": "计划不存在"}
    return {"success": True, "plan": plan}


@router.put("/agent/{agent_id}/plans/{plan_id}/status")
async def mu_agent_plan_status(agent_id: int, plan_id: int, body: MuPlanStatusRequest,
                               user: dict = Depends(get_mu_user)):
    try:
        plan = plan_store.update_plan_status(user["id"], plan_id, body.status)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    if plan is None:
        return {"success": False, "error": "计划不存在"}
    return {"success": True, "plan": plan}


@router.delete("/agent/{agent_id}/plans/{plan_id}")
async def mu_agent_plan_delete(agent_id: int, plan_id: int, user: dict = Depends(get_mu_user)):
    ok = plan_store.delete_plan(user["id"], plan_id)
    return {"success": ok, "message": "计划已删除" if ok else "计划不存在"}


@router.post("/search_memory")
async def mu_search_memory(request: Dict[str, Any], user: dict = Depends(get_mu_user)):
    try:
        query = (request or {}).get("query", "")
        agent_id = (request or {}).get("agent_id", None)
        max_results = (request or {}).get("max_results", 10)
        results = agent_store.search_memory(user["id"], query, agent_id=agent_id,
                                            limit=max_results)
        return {"success": True, "query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ 知识库 RAG（user_id 隔离） ============

class KnowledgeMuSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    threshold: float = 0.3


@router.post("/knowledge/upload")
async def mu_knowledge_upload(files: List[UploadFile] = File(...),
                              user: dict = Depends(check_user_rate)):
    """上传文档到该用户知识库：保存到 uploads_dir(user_id) 后抽取文本入库"""
    ensure_db()
    from lobster_mu.paths import uploads_dir, gen_filename
    from lobster_mu.upload_service import extract_text

    results = []
    for file in files:
        try:
            content = await file.read()
            ext = os.path.splitext(file.filename or "")[1][:16].lower()
            file_path = os.path.join(uploads_dir(user["id"]), gen_filename(file.filename))
            with open(file_path, "wb") as f:
                f.write(content)

            # 文本抽取与本地 embedding 均为 CPU 密集，必须丢到线程池执行，
            # 避免阻塞 asyncio 事件循环导致全站不可用。
            text_content = await asyncio.to_thread(extract_text, file_path, ext, raw=content)
            result = await asyncio.to_thread(
                knowledge_store.add_document,
                user["id"], file.filename, len(content), text_content,
                os.path.basename(file_path),
            )
            results.append({
                "success": True,
                "doc_id": result["doc_id"],
                "filename": file.filename,
                "chunk_count": result["chunk_count"],
                "file_size": result["file_size"],
            })
        except ValueError as e:
            results.append({"success": False, "filename": file.filename, "error": str(e)})
        except Exception as e:
            results.append({"success": False, "filename": file.filename, "error": str(e)})
    return {"success": all(r.get("success") for r in results), "results": results}


@router.get("/knowledge/list")
async def mu_knowledge_list(user: dict = Depends(get_mu_user)):
    return {"success": True, "data": knowledge_store.list_documents(user["id"])}


@router.delete("/knowledge/{doc_id}")
async def mu_knowledge_delete(doc_id: str, user: dict = Depends(get_mu_user)):
    deleted = knowledge_store.delete_document(user["id"], doc_id)
    if deleted is None:
        return {"success": False, "error": "文档不存在"}
    return {"success": True, "message": f"已删除文档，清理了 {deleted} 个分块"}


@router.post("/knowledge/search")
async def mu_knowledge_search(body: KnowledgeMuSearchRequest,
                              user: dict = Depends(get_mu_user)):
    try:
        # search 内含本地 embed_query（CPU 密集），丢线程池避免阻塞事件循环
        results = await asyncio.to_thread(
            knowledge_store.search, user["id"], body.query, body.top_k, body.threshold
        )
        return {"success": True, "data": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/knowledge/stats")
async def mu_knowledge_stats(user: dict = Depends(get_mu_user)):
    return {"success": True, "data": knowledge_store.stats(user["id"])}


@router.get("/admin/knowledge")
async def admin_knowledge_overview(admin: dict = Depends(require_admin)):
    """管理员查看所有用户的知识库情况（含共享文档统计）"""
    ensure_db()
    return {"success": True, "data": knowledge_store.admin_all_users_knowledge()}


@router.get("/admin/knowledge/doc/{doc_id}")
async def admin_knowledge_doc(doc_id: str, admin: dict = Depends(require_admin)):
    """管理员查看某知识库文档的提取文本内容"""
    ensure_db()
    doc = knowledge_store.admin_get_doc_content(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"success": True, "file": doc}


@router.get("/admin/knowledge/doc/{doc_id}/chunks")
async def admin_knowledge_doc_chunks(doc_id: str, admin: dict = Depends(require_admin)):
    """管理员按块查看某知识库文档的分块内容"""
    ensure_db()
    doc = knowledge_store.admin_get_doc_chunks(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"success": True, "doc": doc}


@router.get("/admin/knowledge/doc/{doc_id}/raw")
async def admin_knowledge_doc_raw(doc_id: str, download: int = 0, admin: dict = Depends(require_admin)):
    """管理员取某知识库文档的原始文件（默认 inline 供 Office/PDF 预览；?download=1 强制下载）"""
    from fastapi.responses import FileResponse
    from lobster_mu.paths import uploads_dir
    ensure_db()
    info = knowledge_store.admin_get_doc_file(doc_id)
    if not info:
        raise HTTPException(status_code=404, detail="原始文件不存在")
    path = os.path.join(uploads_dir(info["user_id"]), info["stored_name"])
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="原始文件不存在")
    if download:
        return FileResponse(path, filename=info["filename"] or os.path.basename(path))
    return FileResponse(path)


@router.post("/admin/knowledge/doc/{doc_id}/public")
async def admin_knowledge_set_public(doc_id: str, body: dict, admin: dict = Depends(require_admin)):
    """管理员设置/取消某知识库文档为公共（所有用户检索可命中）"""
    ensure_db()
    result = knowledge_store.set_public(doc_id, bool((body or {}).get("is_public")))
    if result is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"success": True, "doc": result}


@router.get("/admin/knowledge/index-status")
async def admin_knowledge_index_status(admin: dict = Depends(require_admin)):
    """Chroma HNSW 向量索引状态：是否可用 + 索引条目数 + 理论应有条目数"""
    ensure_db()
    from lobster_mu import vector_index
    conn = db.get_conn()
    try:
        expected = conn.execute(
            "SELECT COALESCE(SUM(chunk_count), 0) AS s FROM mu_knowledge_docs"
        ).fetchone()["s"]
    finally:
        conn.close()
    return {
        "available": vector_index.available(),
        "indexed": vector_index.index_count(),
        "expected": int(expected or 0),
    }


@router.post("/admin/knowledge/reindex")
async def admin_knowledge_reindex(mode: str = "sync", admin: dict = Depends(require_admin)):
    """管理员重建 Chroma 向量索引。
    mode=sync（默认）：增量补齐缺失条目，快；mode=full：全量重建到新目录后切换，慢但可修复损坏。"""
    ensure_db()
    from lobster_mu import vector_index
    if mode == "full":
        result = await asyncio.to_thread(vector_index.rebuild_index)
    else:
        result = await asyncio.to_thread(vector_index.sync_index)
    ok = result.get("success", True) and "error" not in result
    return {"success": bool(ok), "mode": mode, "result": result}


@router.get("/admin/model-speed")
async def admin_model_speed(apply: int = 0, admin: dict = Depends(require_admin)):
    """管理员查看各模型首字输出速度（TTFT）排名；?apply=1 时立即切换默认模型到最快"""
    from llm.model_speed_stats import get_model_speed_ranking, apply_fastest_default
    from models.model_manager import ModelManager
    ranking = get_model_speed_ranking()
    mm = ModelManager()
    text_models = [m for m in mm.get_all() if m.api_key and m.model_type == "text"]
    current_default = text_models[0].model_name if text_models else None
    switched_to = apply_fastest_default() if apply else None
    return {"success": True, "data": {
        "ranking": ranking,
        "current_default": current_default,
        "switched_to": switched_to,
    }}


@router.get("/admin/usage-ranking")
async def admin_usage_ranking(admin: dict = Depends(require_admin)):
    """管理员查看用户大模型使用排行：按调用次数降序，含各模型调用次数与 token 用量。

    数据源：mu_chat_messages 中 role='assistant' 的行即一次模型调用，
    每行带 model_name 与 token_stats（JSON: prompt/completion/total tokens）。
    """
    ensure_db()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT user_id, model_name, token_stats FROM mu_chat_messages WHERE role = 'assistant'"
        ).fetchall()
    finally:
        conn.close()

    # 按用户聚合：总调用数、各模型调用数、token 汇总
    users_stat = {}  # user_id -> dict
    for r in rows:
        uid = r["user_id"]
        st = users_stat.setdefault(uid, {
            "user_id": uid, "total_calls": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "models": {},  # model_name -> {calls, prompt_tokens, completion_tokens, total_tokens}
        })
        st["total_calls"] += 1
        model = r["model_name"] or "未知模型"
        m = st["models"].setdefault(model, {
            "model_name": model, "calls": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        })
        m["calls"] += 1
        # 解析 token_stats
        pt = ct = tt = 0
        raw = r["token_stats"]
        if raw:
            try:
                obj = _json.loads(raw) if isinstance(raw, str) else raw
                pt = int(obj.get("prompt_tokens") or 0)
                ct = int(obj.get("completion_tokens") or 0)
                tt = int(obj.get("total_tokens") or (pt + ct))
            except Exception:
                pass
        st["prompt_tokens"] += pt
        st["completion_tokens"] += ct
        st["total_tokens"] += tt
        m["prompt_tokens"] += pt
        m["completion_tokens"] += ct
        m["total_tokens"] += tt

    # 关联用户信息，按总调用次数降序
    ranking = []
    for uid, st in users_stat.items():
        u = user_store.get_by_id(uid)
        st["username"] = u["username"] if u else f"#{uid}"
        st["display_name"] = (u["display_name"] if u else "") or st["username"]
        st["role"] = u["role"] if u else "user"
        # models 转为列表并按调用次数降序
        st["models"] = sorted(st["models"].values(), key=lambda x: x["calls"], reverse=True)
        ranking.append(st)
    ranking.sort(key=lambda x: x["total_calls"], reverse=True)

    return {"success": True, "ranking": ranking}


@router.post("/admin/db-maintenance")
async def admin_db_maintenance(admin: dict = Depends(require_admin)):
    """管理员触发数据库维护：checkpoint + VACUUM + ANALYZE。

    用于修复「随时间查询变慢」：回收删除大字段（向量等）留下的空闲页、
    收缩 WAL、更新查询统计。VACUUM 在大库上可能耗时数十秒，故放到线程池
    执行，避免同步阻塞整个 async 事件循环（否则期间所有请求的 TTFB 都会飙高）。
    """
    ensure_db()
    info = await asyncio.to_thread(db.db_maintenance)
    return {"success": True, "info": info}


# ============ Skills（全局只读 + 以用户身份执行） ============

class SkillMuExecuteRequest(BaseModel):
    skill_name: str
    parameters: Optional[Dict[str, Any]] = None


@router.get("/skills/discover")
async def mu_skills_discover(user: dict = Depends(get_mu_user)):
    from web.routes.lobster_claw import discover_skills
    skills = discover_skills()
    return {"success": True, "skills": skills, "count": len(skills)}


@router.get("/skills/{skill_name}")
async def mu_skill_detail(skill_name: str, user: dict = Depends(get_mu_user)):
    from web.routes.lobster_claw import load_skill
    skill = load_skill(skill_name)
    if not skill:
        return {"success": False, "error": f"技能不存在: {skill_name}"}
    return {"success": True, "skill": skill}


@router.post("/skills/execute")
async def mu_skill_execute(body: SkillMuExecuteRequest, user: dict = Depends(get_mu_user)):
    """照抄原版 execute 端点流程（load_skill + get_skill_configs/BaseSkill），保持行为一致"""
    from web.routes.lobster_claw import load_skill
    skill = load_skill(body.skill_name)
    if not skill:
        return {"success": False, "error": f"技能不存在: {body.skill_name}"}
    try:
        from skills.skill_manager import get_skill_configs

        configs = get_skill_configs()
        skill_config = next(
            (c for c in configs if c.name.lower() == body.skill_name.lower()), None
        )
        if skill_config:
            from skills.base import BaseSkill
            skill_instance = BaseSkill.from_config(skill_config)
            result = await skill_instance.execute(body.parameters or {})
            return {
                "success": True,
                "skill": body.skill_name,
                "title": skill.get("title", body.skill_name),
                "description": skill.get("description", ""),
                "result": result,
                "type": "configured_skill",
            }
        return {
            "success": True,
            "skill": body.skill_name,
            "title": skill.get("title", body.skill_name),
            "description": skill.get("description", ""),
            "message": "技能已加载，但未在系统中配置执行器",
            "type": "discovered_skill",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "skill": body.skill_name}


# ============ 飞书（全局共享配置，仅管理员可查看/修改，转发原版端点函数） ============

from web.routes.lobster_claw import FeishuConfigUpdate  # noqa: E402 (转发复用请求模型)


@router.get("/feishu/config")
async def mu_feishu_get_config(admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import get_feishu_config
    return await get_feishu_config()


@router.post("/feishu/config")
async def mu_feishu_update_config(body: FeishuConfigUpdate,
                                  admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import update_feishu_config
    return await update_feishu_config(body)


@router.post("/feishu/test-connection")
async def mu_feishu_test_connection(admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import test_feishu_connection
    return await test_feishu_connection()


@router.get("/feishu/status")
async def mu_feishu_status(admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import get_feishu_status
    return await get_feishu_status()


@router.get("/feishu/messages")
async def mu_feishu_messages(limit: int = 50, offset: int = 0,
                             admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import get_feishu_messages
    return await get_feishu_messages(limit=limit, offset=offset)


@router.delete("/feishu/messages")
async def mu_feishu_clear_messages(admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import clear_feishu_messages
    return await clear_feishu_messages()


@router.get("/feishu/sessions")
async def mu_feishu_sessions(admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import get_feishu_sessions
    return await get_feishu_sessions()


@router.get("/feishu/sessions/{session_id}")
async def mu_feishu_session_detail(session_id: str, admin: dict = Depends(require_admin)):
    from web.routes.lobster_claw import get_feishu_session_detail
    return await get_feishu_session_detail(session_id)


# ============ MCP server 管理（MCP 工具生态入口） ============

class McpServerRequest(BaseModel):
    name: str
    transport: str = "stdio"  # stdio / sse / http
    command: Optional[str] = ""
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = ""
    headers: Optional[Dict[str, str]] = None  # sse/http 自定义请求头（如 Authorization）
    enabled: bool = True


@router.get("/mcp/servers")
async def mu_mcp_list(user: dict = Depends(get_mu_user)):
    from lobster_mu import mcp_store, mcp_client
    servers = mcp_store.list_servers(user["id"])
    for srv in servers:
        cached = mcp_client.get_cached_tools(user["id"], srv["id"])
        srv["tool_count_cached"] = len(cached) if cached is not None else None
    return {"success": True, "servers": servers, "mcp_available": mcp_client.MCP_AVAILABLE}


@router.post("/mcp/servers")
async def mu_mcp_create(body: McpServerRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_store, mcp_client
    if body.transport not in ("stdio", "sse", "http", "streamable-http"):
        raise HTTPException(status_code=400, detail="transport 仅支持 stdio / sse / http")
    if body.transport == "stdio" and not body.command:
        raise HTTPException(status_code=400, detail="stdio 类型必须填写 command")
    if body.transport in ("sse", "http", "streamable-http") and not body.url:
        raise HTTPException(status_code=400, detail="sse/http 类型必须填写 url")
    srv = mcp_store.create_server(
        user["id"], body.name, body.transport,
        command=body.command or "", args=body.args or [],
        env=body.env or {}, url=body.url or "", enabled=body.enabled,
        headers=body.headers or {},
    )
    mcp_client.invalidate_cache(user["id"], srv["id"])
    return {"success": True, "server": srv}


@router.put("/mcp/servers/{server_id}")
async def mu_mcp_update(server_id: int, body: McpServerRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_store, mcp_client
    if not mcp_store.get_server(user["id"], server_id):
        raise HTTPException(status_code=404, detail="MCP server 不存在")
    fields = body.model_dump(exclude_none=True)
    srv = mcp_store.update_server(user["id"], server_id, fields)
    mcp_client.invalidate_cache(user["id"], server_id)
    return {"success": True, "server": srv}


@router.delete("/mcp/servers/{server_id}")
async def mu_mcp_delete(server_id: int, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_store, mcp_client
    ok = mcp_store.delete_server(user["id"], server_id)
    mcp_client.invalidate_cache(user["id"], server_id)
    return {"success": ok, "message": "已删除" if ok else "server 不存在"}


@router.post("/mcp/servers/{server_id}/toggle")
async def mu_mcp_toggle(server_id: int, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_store, mcp_client
    srv = mcp_store.toggle_server(user["id"], server_id)
    if not srv:
        raise HTTPException(status_code=404, detail="MCP server 不存在")
    mcp_client.invalidate_cache(user["id"], server_id)
    return {"success": True, "server": srv}


@router.post("/mcp/servers/{server_id}/test")
async def mu_mcp_test(server_id: int, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_store, mcp_client
    raw = mcp_store.get_server_raw(user["id"], server_id)
    if not raw:
        raise HTTPException(status_code=404, detail="MCP server 不存在")
    result = await asyncio.to_thread(mcp_client.refresh_server_tools, user["id"], server_id, raw)
    return {"success": result["success"], "tools": result.get("tools", []),
            "error": result.get("error"), "tool_count": len(result.get("tools", []))}


@router.get("/mcp/servers/{server_id}/tools")
async def mu_mcp_tools(server_id: int, refresh: bool = False, user: dict = Depends(get_mu_user)):
    from lobster_mu import mcp_store, mcp_client
    srv = mcp_store.get_server(user["id"], server_id)
    if not srv:
        raise HTTPException(status_code=404, detail="MCP server 不存在")
    tools = mcp_client.get_cached_tools(user["id"], server_id)
    if tools is None or refresh:
        raw = mcp_store.get_server_raw(user["id"], server_id)
        result = await asyncio.to_thread(mcp_client.refresh_server_tools, user["id"], server_id, raw)
        if not result["success"]:
            return {"success": False, "error": result["error"], "tools": []}
        tools = result["tools"]
    return {"success": True, "tools": tools}


# ============ MCP 服务端（本系统作为 MCP server：配置化 API 封装 + 令牌管理） ============

class McpToolConfigRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    url: str
    method: Optional[str] = "GET"
    headers: Optional[Dict[str, str]] = None
    query_params: Optional[Dict[str, str]] = None
    body_template: Optional[str] = ""
    params_schema: Optional[List[Dict[str, Any]]] = None
    timeout: Optional[int] = 30


@router.get("/mcp-server/tools")
async def mu_mcpsrv_list_tools(user: dict = Depends(get_mu_user)):
    from lobster_mu import mcp_tool_store
    return {"success": True, "tools": mcp_tool_store.list_tools(user["id"])}


@router.post("/mcp-server/tools")
async def mu_mcpsrv_create_tool(body: McpToolConfigRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_tool_store
    result = mcp_tool_store.create_tool(user["id"], body.model_dump(exclude_none=True))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    tools.log_operation(user["id"], "mcp_tool_create", f"创建MCP工具: {body.name}", ip="")
    return result


@router.put("/mcp-server/tools/{tool_id}")
async def mu_mcpsrv_update_tool(tool_id: int, body: McpToolConfigRequest,
                                user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_tool_store
    result = mcp_tool_store.update_tool(user["id"], tool_id, body.model_dump(exclude_none=True))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/mcp-server/tools/{tool_id}")
async def mu_mcpsrv_delete_tool(tool_id: int, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_tool_store
    result = mcp_tool_store.delete_tool(user["id"], tool_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/mcp-server/tools/{tool_id}/toggle")
async def mu_mcpsrv_toggle_tool(tool_id: int, body: Dict[str, bool] = Body(...),
                                user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_tool_store
    result = mcp_tool_store.toggle_tool(user["id"], tool_id, bool(body.get("enabled", True)))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/mcp-server/tools/{tool_id}/test")
async def mu_mcpsrv_test_tool(tool_id: int, body: Dict[str, Any] = Body(default={}),
                              user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_tool_store, mcp_tool_executor
    tool = mcp_tool_store.get_tool(user["id"], tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    args = body.get("arguments") if isinstance(body, dict) else None
    result = await mcp_tool_executor.execute_api_tool(user["id"], tool, args or {})
    return {"success": True, "result": result}


class McpTokenCreateRequest(BaseModel):
    name: Optional[str] = ""
    expires_at: Optional[str] = ""


@router.get("/mcp-server/tokens")
async def mu_mcpsrv_list_tokens(user: dict = Depends(get_mu_user)):
    from lobster_mu import mcp_token_store
    return {"success": True, "tokens": mcp_token_store.list_tokens(user["id"])}


@router.post("/mcp-server/tokens")
async def mu_mcpsrv_create_token(body: McpTokenCreateRequest, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_token_store
    row, plaintext = mcp_token_store.create_token(user["id"], body.name or "", body.expires_at or "")
    tools.log_operation(user["id"], "mcp_token_create", f"创建MCP令牌: {row['prefix']}...", ip="")
    # 明文仅此一次返回，前端须提示用户立即保存
    return {"success": True, "token": row, "plaintext": plaintext}


@router.delete("/mcp-server/tokens/{token_id}")
async def mu_mcpsrv_revoke_token(token_id: int, user: dict = Depends(check_user_rate)):
    from lobster_mu import mcp_token_store
    result = mcp_token_store.revoke_token(user["id"], token_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    tools.log_operation(user["id"], "mcp_token_revoke", f"吊销MCP令牌#{token_id}", ip="")
    return result


@router.get("/mcp-server/endpoint-info")
async def mu_mcpsrv_endpoint_info(request: Request, user: dict = Depends(get_mu_user)):
    from lobster_mu import mcp_server as _ms
    base = str(request.base_url).rstrip("/")
    endpoint = f"{base}/mcp"
    return {
        "success": True,
        "available": _ms.MCP_SERVER_AVAILABLE,
        "endpoint": endpoint,
        "transport": "streamable-http",
        "client_config_example": {
            "mcpServers": {
                "lobster-mu": {
                    "url": endpoint,
                    "headers": {"Authorization": "Bearer <在此粘贴你的令牌>"}
                }
            }
        },
    }
