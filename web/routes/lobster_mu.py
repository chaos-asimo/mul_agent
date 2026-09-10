# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 路由层（前缀 /api/lobster-mu）"""
import os
from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile, Form
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

from lobster_mu import db, user_store
from lobster_mu.security import verify_password, get_mu_user, require_admin

router = APIRouter(prefix="/api/lobster-mu")

_db_ready = False


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


@router.post("/login")
async def mu_login(request: Request, body: MuLoginRequest):
    ensure_db()
    row = user_store.get_by_username(body.username)
    if not row or row["disabled"] or not verify_password(body.password, row["salt"], row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    request.session["mu_user"] = {"id": row["id"], "username": row["username"], "role": row["role"]}
    user_store.update_last_login(row["id"])
    return {"status": "success", "user": {"id": row["id"], "username": row["username"], "role": row["role"]}}


@router.post("/logout")
async def mu_logout(request: Request):
    request.session.pop("mu_user", None)
    return {"status": "success", "message": "退出成功"}


# ============ 直接登录（按用户名/显示名，不存在则自动创建） ============

class MuDirectLoginRequest(BaseModel):
    username: str
    display_name: str


@router.post("/login/direct")
async def mu_login_direct(request: Request, body: MuDirectLoginRequest):
    """按用户名直接登录；若用户不存在则自动新建（密码固定为 用户名+sy），已存在则直接登录。"""
    ensure_db()
    username = (body.username or "").strip()
    display_name = (body.display_name or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not display_name:
        raise HTTPException(status_code=400, detail="显示名不能为空")

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
        raise HTTPException(status_code=403, detail="账号已禁用")

    request.session["mu_user"] = {"id": row["id"], "username": row["username"], "role": row["role"]}
    user_store.update_last_login(row["id"])
    return {
        "status": "success",
        "user": {"id": row["id"], "username": row["username"], "role": row["role"]},
        "created": created,
    }


@router.get("/me")
async def mu_me(user: dict = Depends(get_mu_user)):
    return {"user": user}


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


@router.get("/admin/users")
async def admin_list_users(admin: dict = Depends(require_admin)):
    ensure_db()
    return {"users": user_store.list_users()}


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
async def mu_chat_message(body: ChatMessageRequest, user: dict = Depends(check_user_rate)):
    return chat_service.chat_message_once(user["id"], body)


@router.post("/chat/stream")
async def mu_chat_stream(body: ChatStreamRequest, user: dict = Depends(check_user_rate)):
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


@router.delete("/chat/sessions")
async def mu_chat_sessions_clear(user: dict = Depends(get_mu_user)):
    session_store.clear_sessions(user["id"])
    return {"success": True, "message": "所有会话已清空"}


# ============ 文件上传 ============

@router.post("/upload")
async def mu_upload(files: List[UploadFile] = File(...), user: dict = Depends(check_user_rate)):
    results = []
    for file in files:
        try:
            content = await file.read()
            if len(content) > upload_service.MAX_UPLOAD_SIZE:
                results.append({"success": False, "filename": file.filename, "error": "文件超过10MB限制"})
                continue
            info = upload_service.save_upload(user["id"], file.filename, content)
            results.append({
                "success": True,
                "id": info["path"],
                "filename": file.filename,
                "size": info["size"],
                "content_preview": info["content"][:200] if info["content"] else "",
            })
        except Exception as e:
            results.append({"success": False, "filename": file.filename, "error": str(e)})
    return {"results": results}


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


@router.get("/script/installation-status")
async def mu_script_install_status(user: dict = Depends(get_mu_user)):
    return script_service.get_installation_status(user["id"])


@router.get("/script/files/download/{file_name}")
async def mu_script_file_download(file_name: str, user: dict = Depends(get_mu_user)):
    from fastapi.responses import FileResponse
    try:
        path = script_service.get_generated_file_path(user["id"], file_name)
    except ValueError:
        raise HTTPException(status_code=403, detail="无权访问该文件")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=os.path.basename(path))


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
    from lobster_mu import tools
    if not tools.is_command_safe(body.command):
        tools.log_operation(user["id"], "exec", body.command[:100], success=False, error="危险命令")
        return {"success": False, "error": "危险命令禁止执行"}
    result = await _async_shell(body.command, body.timeout)
    tools.log_operation(user["id"], "exec", body.command[:100], success=result.get("success", False))
    return result


async def _async_shell(command: str, timeout: int) -> Dict[str, Any]:
    import asyncio
    import subprocess as _sp
    try:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=_sp.PIPE, stderr=_sp.PIPE, shell=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "success": True,
            "stdout": stdout.decode('utf-8', errors='replace'),
            "stderr": stderr.decode('utf-8', errors='replace'),
            "return_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": f"命令执行超时（{timeout}秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}


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

            text_content = extract_text(file_path, ext, raw=content)
            result = knowledge_store.add_document(user["id"], file.filename, len(content),
                                                  text_content)
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
        results = knowledge_store.search(user["id"], body.query, top_k=body.top_k,
                                         threshold=body.threshold)
        return {"success": True, "data": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/knowledge/stats")
async def mu_knowledge_stats(user: dict = Depends(get_mu_user)):
    return {"success": True, "data": knowledge_store.stats(user["id"])}


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
    result = mcp_client.refresh_server_tools(user["id"], server_id, raw)
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
        result = mcp_client.refresh_server_tools(user["id"], server_id, raw)
        if not result["success"]:
            return {"success": False, "error": result["error"], "tools": []}
        tools = result["tools"]
    return {"success": True, "tools": tools}
