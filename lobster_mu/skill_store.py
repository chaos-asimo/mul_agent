# -*- coding: utf-8 -*-
"""多用户技能(Skill)仓库：SQLite 存储，按 user_id 隔离 + 管理员公共技能。

设计要点：
- 私有技能：user_id=所有者，is_public=0，仅所有者可见/可改/可执行。
- 公共技能：is_public=1（user_id 通常=0，管理员发布），所有用户可见可执行，仅管理员可改。
- 完整 SkillConfig 存 config_json（复用 skills.skill_config.SkillConfig），
  同时冗余 name/description/skill_type/executor/enabled 列便于查询与展示。
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from lobster_mu.db import get_conn


def _now() -> str:
    return datetime.now().isoformat()


def _row_to_dict(row) -> Dict[str, Any]:
    """把一行 + config_json 合并成前端可用的技能 dict"""
    cfg = {}
    try:
        cfg = json.loads(row["config_json"] or "{}")
    except Exception:
        cfg = {}
    return {
        "skill_id": row["skill_id"],
        "id": row["skill_id"],  # 兼容前端以 id 引用
        "name": row["name"],
        "description": row["description"],
        "skill_type": row["skill_type"],
        "executor": row["executor"],
        "enabled": bool(row["enabled"]),
        "is_public": bool(row["is_public"]),
        "owner_user_id": row["user_id"],
        "config": cfg,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _config_from_payload(skill_data: Dict[str, Any]) -> Dict[str, Any]:
    """从前端 payload 规整出存储用的 config_json（尽量兼容 SkillConfig 字段）"""
    cfg = dict(skill_data.get("config") or {})
    # 顶层字段优先回填到 config，保证 SkillConfig.from_dict 可用
    for k in ("name", "description", "skill_type", "executor", "script",
              "prompt_template", "api_endpoint", "parameters", "input_type",
              "output_type", "tags", "icon", "timeout", "retry_count", "priority",
              "trigger", "version", "author"):
        if k in skill_data and skill_data[k] is not None:
            cfg[k] = skill_data[k]
    cfg.setdefault("name", skill_data.get("name", ""))
    cfg.setdefault("executor", skill_data.get("executor", "llm"))
    return cfg


# ============ 查询 ============

def list_my_skills(user_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_skills WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_public() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_skills WHERE is_public = 1 ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_all() -> List[Dict[str, Any]]:
    """管理员视角：全部技能（含公共与各用户私有），公共在前"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_skills ORDER BY is_public DESC, created_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_skills(user_id: int) -> List[Dict[str, Any]]:
    """我的私有技能 + 公共技能（去重，公共在前）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_skills WHERE user_id = ? OR is_public = 1 "
            "ORDER BY is_public DESC, created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_enabled(user_id: int) -> List[Dict[str, Any]]:
    """对话注入用：已启用的 我的 + 公共"""
    return [s for s in list_skills(user_id) if s.get("enabled")]


def get(user_id: int, skill_id: str) -> Optional[Dict[str, Any]]:
    """取当前用户可见的技能（自己的或公共的），越权返回 None"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_skills WHERE skill_id = ? AND (user_id = ? OR is_public = 1)",
            (skill_id, user_id),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def _get_raw(skill_id: str) -> Optional[Dict[str, Any]]:
    """内部：取任意一行（含归属判断用），不做可见性过滤"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM mu_skills WHERE skill_id = ?", (skill_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


# ============ 写操作（带归属校验） ============

def _can_write(skill: Optional[Dict[str, Any]], user_id: int, is_admin: bool) -> bool:
    if not skill:
        return False
    if skill.get("is_public"):
        return bool(is_admin)  # 公共技能仅管理员可写
    return skill.get("owner_user_id") == user_id


def add(user_id: int, skill_data: Dict[str, Any], is_public: bool = False,
        is_admin: bool = False) -> Dict[str, Any]:
    if is_public and not is_admin:
        return {"success": False, "error": "仅管理员可创建公共技能"}
    cfg = _config_from_payload(skill_data)
    skill_id = skill_data.get("skill_id") or skill_data.get("id") or str(uuid.uuid4())
    name = cfg.get("name") or skill_data.get("name") or "未命名技能"
    description = cfg.get("description") or skill_data.get("description") or ""
    skill_type = cfg.get("skill_type") or skill_data.get("skill_type") or "custom"
    executor = cfg.get("executor") or skill_data.get("executor") or "llm"
    enabled = 1 if skill_data.get("enabled", True) else 0
    owner = 0 if is_public else user_id
    now = _now()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO mu_skills (user_id, skill_id, name, description, skill_type, "
            "executor, enabled, is_public, config_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (owner, skill_id, name, description, skill_type, executor, enabled,
             1 if is_public else 0, json.dumps(cfg, ensure_ascii=False), now, now),
        )
        conn.commit()
    except Exception as e:
        return {"success": False, "error": f"创建失败: {e}"}
    finally:
        conn.close()
    return {"success": True, "skill": get(owner if is_public else user_id, skill_id),
            "skill_id": skill_id}


def update(user_id: int, skill_id: str, skill_data: Dict[str, Any],
           is_admin: bool = False) -> Dict[str, Any]:
    skill = _get_raw(skill_id)
    if not _can_write(skill, user_id, is_admin):
        return {"success": False, "error": "无权修改该技能"}
    cfg = _config_from_payload(skill_data)
    name = cfg.get("name") or skill["name"]
    description = cfg.get("description") or skill["description"]
    skill_type = cfg.get("skill_type") or skill["skill_type"]
    executor = cfg.get("executor") or skill["executor"]
    enabled = skill_data["enabled"] if "enabled" in skill_data else skill["enabled"]
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE mu_skills SET name=?, description=?, skill_type=?, executor=?, "
            "enabled=?, config_json=?, updated_at=? WHERE skill_id=?",
            (name, description, skill_type, executor, 1 if enabled else 0,
             json.dumps(cfg, ensure_ascii=False), _now(), skill_id),
        )
        conn.commit()
    except Exception as e:
        return {"success": False, "error": f"更新失败: {e}"}
    finally:
        conn.close()
    return {"success": True, "skill": get(skill["owner_user_id"], skill_id)}


def delete(user_id: int, skill_id: str, is_admin: bool = False) -> Dict[str, Any]:
    skill = _get_raw(skill_id)
    if not _can_write(skill, user_id, is_admin):
        return {"success": False, "error": "无权删除该技能"}
    conn = get_conn()
    try:
        conn.execute("DELETE FROM mu_skills WHERE skill_id=?", (skill_id,))
        conn.commit()
    except Exception as e:
        return {"success": False, "error": f"删除失败: {e}"}
    finally:
        conn.close()
    return {"success": True}


def set_enabled(user_id: int, skill_id: str, enabled: bool,
                is_admin: bool = False) -> Dict[str, Any]:
    skill = _get_raw(skill_id)
    if not _can_write(skill, user_id, is_admin):
        return {"success": False, "error": "无权操作该技能"}
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE mu_skills SET enabled=?, updated_at=? WHERE skill_id=?",
            (1 if enabled else 0, _now(), skill_id),
        )
        conn.commit()
    except Exception as e:
        return {"success": False, "error": f"操作失败: {e}"}
    finally:
        conn.close()
    return {"success": True}


def set_public(skill_id: str, is_public: bool, is_admin: bool = False) -> Dict[str, Any]:
    """设置技能是否为公共（仅管理员）。设为公共时归属转到管理员(user_id=0)。"""
    if not is_admin:
        return {"success": False, "error": "仅管理员可设置公共技能"}
    skill = _get_raw(skill_id)
    if not skill:
        return {"success": False, "error": "技能不存在"}
    conn = get_conn()
    try:
        if is_public:
            conn.execute(
                "UPDATE mu_skills SET is_public=1, user_id=0, updated_at=? WHERE skill_id=?",
                (_now(), skill_id),
            )
        else:
            conn.execute(
                "UPDATE mu_skills SET is_public=0, updated_at=? WHERE skill_id=?",
                (_now(), skill_id),
            )
        conn.commit()
    except Exception as e:
        return {"success": False, "error": f"操作失败: {e}"}
    finally:
        conn.close()
    return {"success": True}


# ============ 执行 ============

def _fill_template(template: str, params: Dict[str, Any]) -> str:
    """用 params 填充 {占位符}；缺失占位符保留原样"""
    if not template:
        return ""
    out = template
    for k, v in (params or {}).items():
        out = out.replace("{" + str(k) + "}", str(v))
    return out


def _call_llm(prompt: str, system: str = None) -> str:
    from web.routes.lobster_claw import get_default_llm_adapter
    adapter = get_default_llm_adapter()
    if not adapter:
        raise RuntimeError("未配置可用的 LLM 适配器")
    sys = system if system else "你是一个技能执行助手，请按要求完成任务。"
    messages = adapter.create_prompt(sys, prompt, [])
    resp = adapter.chat(messages)
    if isinstance(resp, dict):
        return resp.get("content") or resp.get("result") or str(resp)
    return str(resp)


def execute(user_id: int, skill_id: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """执行技能。任何异常都捕获并返回 success:false，绝不抛出。"""
    params = params or {}
    try:
        skill = get(user_id, skill_id)
        if not skill:
            return {"success": False, "error": "技能不存在或无权访问"}
        if not skill.get("enabled"):
            return {"success": False, "error": "技能已禁用"}
        cfg = skill.get("config") or {}
        executor = (cfg.get("executor") or skill.get("executor") or "llm").lower()
        is_skillmd = cfg.get("source") == "skillmd" or "skillmd_body" in cfg

        # 标准技能包：可指定运行其内置脚本
        if is_skillmd and params.get("run_script"):
            scripts = cfg.get("scripts") or {}
            code = scripts.get(params["run_script"])
            if not code:
                return {"success": False, "error": f"脚本不存在: {params['run_script']}"}
            from lobster_mu import script_service
            exec_result = script_service.execute_python_script(user_id, code)
            if isinstance(exec_result, dict) and not exec_result.get("success", True):
                return {"success": False, "error": exec_result.get("error") or exec_result.get("result") or "执行失败"}
            return {"success": True, "result": (exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result))}

        if executor == "llm":
            body = cfg.get("skillmd_body") or cfg.get("prompt_template", "")
            if is_skillmd:
                # 正文作为系统指令，用户参数作为输入
                user_input = "\n".join(f"{k}: {v}" for k, v in params.items()) if params else ""
                prompt = body
                if user_input:
                    prompt = (body or "") + "\n\n【用户输入】\n" + user_input
            else:
                prompt = _fill_template(cfg.get("prompt_template", ""), params)
            if not prompt.strip():
                prompt = "\n".join(f"{k}: {v}" for k, v in params.items())
            result = _call_llm(prompt, system=body if is_skillmd else None)
            return {"success": True, "result": result}

        if executor == "script":
            from lobster_mu import script_service
            code = cfg.get("script", "")
            if not code:
                return {"success": False, "error": "脚本技能缺少 script 代码"}
            exec_result = script_service.execute_python_script(user_id, code)
            if isinstance(exec_result, dict):
                if not exec_result.get("success", True):
                    return {"success": False, "error": exec_result.get("error") or exec_result.get("result") or "执行失败"}
                return {"success": True, "result": exec_result.get("result", "")}
            return {"success": True, "result": str(exec_result)}

        if executor in ("search", "web_search"):
            from lobster_mu.tools import web_search
            query = params.get("query") or params.get("content") or ""
            num = int(params.get("num_results") or params.get("num") or 5)
            return {"success": True, "result": web_search(query, num)}

        if executor == "api":
            import httpx
            url = cfg.get("api_endpoint") or params.get("url")
            if not url:
                return {"success": False, "error": "API 技能缺少 endpoint"}
            method = str(params.get("method", "get")).lower()
            with httpx.Client(timeout=30) as client:
                if method == "post":
                    resp = client.post(url, json=params.get("data") or {})
                else:
                    resp = client.get(url, params=params.get("data") or {})
            return {"success": True, "result": resp.text[:10000]}

        return {"success": False, "error": f"不支持的执行器: {executor}"}
    except Exception as e:
        return {"success": False, "error": f"执行失败: {e}"}
