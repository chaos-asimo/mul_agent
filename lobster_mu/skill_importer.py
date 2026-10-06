# -*- coding: utf-8 -*-
"""标准 SKILL.md 技能包导入解析器。

支持三种来源的解析归一：
- 单个 SKILL.md 文本：提取 YAML frontmatter(name/description) + 正文 body。
- zip 技能包：定位包内 SKILL.md，读取 scripts/**、references/**（防路径穿越）。
- 字节流：按内容判定是 markdown 文本还是 zip。

所有函数均不抛异常，失败时在返回结构里带 error 字段，由上层决定。
不引入新依赖（frontmatter 用正则；zip 用标准库 zipfile）。
"""
from __future__ import annotations
import io
import os
import re
import zipfile
from typing import Any, Dict, Optional

# 资源上限（字节）
MAX_SIZE = 5 * 1024 * 1024  # 5MB

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _parse_frontmatter(text: str) -> Dict[str, str]:
    """简易解析 YAML frontmatter 文本（仅取 name / description，兼容大小写与多行 description）。

    不引入 PyYAML：逐行解析 ``key: value``，支持以 ``>`` / ``|`` 开头的折叠/块 scalar
    （取后续缩进行拼接）。无法解析时返回空 dict。
    """
    data: Dict[str, str] = {}
    current_key: Optional[str] = None
    pending_block: Optional[str] = None  # '>' fold | '|' literal
    block_lines = []

    def flush_block():
        if current_key and pending_block is not None:
            if pending_block == ">":
                data[current_key] = " ".join(l.strip() for l in block_lines if l.strip())
            else:
                data[current_key] = "\n".join(block_lines)

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        # 块 scalar 续行：缩进或空行
        if pending_block is not None:
            if line.strip() == "" or line.startswith(" ") or line.startswith("\t"):
                block_lines.append(line)
                continue
            else:
                flush_block()
                pending_block = None
                current_key = None
                block_lines = []
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if not m:
            continue
        key = m.group(1).lower()
        val = m.group(2).strip()
        if val in (">", "|", ">-", "|-", ">+", "|+"):
            current_key = key
            pending_block = ">" if val.startswith(">") else "|"
            block_lines = []
            continue
        # 去掉引号
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if key in ("name", "description"):
            data[key] = val
    flush_block()
    return data


def parse_skill_md(text: str, fallback_name: str = "未命名技能") -> Dict[str, Any]:
    """解析单个 SKILL.md 文本，返回 {name, description, body}。永不抛异常。"""
    try:
        if not isinstance(text, str):
            text = str(text)
        name = fallback_name
        description = ""
        body = text
        m = _FRONTMATTER_RE.match(text)
        if m:
            fm_text, body = m.group(1), m.group(2)
            fm = _parse_frontmatter(fm_text)
            if fm.get("name"):
                name = fm["name"]
            if fm.get("description"):
                description = fm["description"]
        return {"name": (name or fallback_name).strip() or fallback_name,
                "description": description or "",
                "body": body,
                "error": None}
    except Exception as e:  # 兜底绝不抛
        return {"name": fallback_name, "description": "", "body": text or "", "error": str(e)}


def _is_zip_bytes(data: bytes) -> bool:
    return data[:4] == b"PK\x03\x04"


def _safe_member_name(name: str) -> Optional[str]:
    """清洗 zip 成员路径：拒绝绝对路径与 .. 穿越，返回相对名，非法返回 None。"""
    if not name:
        return None
    n = name.replace("\\", "/")
    if n.startswith("/") or ":" in n.split("/")[0]:  # 绝对路径或盘符
        return None
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if ".." in parts:
        return None
    return "/".join(parts)


def parse_zip(data: bytes, fallback_name: str = "未命名技能") -> Dict[str, Any]:
    """解析 zip 技能包，返回 {name, description, body, scripts:{f:c}, references:{f:c}}。

    定位包内 SKILL.md（优先根目录，其次任意首个），读取 scripts/ 与 references/ 下文件。
    防路径穿越：非法成员名跳过。永不抛异常。
    """
    result: Dict[str, Any] = {"name": fallback_name, "description": "", "body": "",
                              "scripts": {}, "references": {}, "source": "skillmd", "error": None}
    try:
        if not _is_zip_bytes(data):
            result["error"] = "不是有效的 zip 文件"
            return result
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            md_candidates = []
            members: Dict[str, bytes] = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                safe = _safe_member_name(info.filename)
                if safe is None:
                    continue  # 跳过穿越/非法路径
                try:
                    content = zf.read(info.filename)
                except Exception:
                    continue
                members[safe] = content
                base = os.path.basename(safe).lower()
                if base == "skill.md":
                    md_candidates.append(safe)
            if not md_candidates:
                result["error"] = "zip 内未找到 SKILL.md"
                return result
            # 优先层级最浅（路径段最少）的 SKILL.md
            md_path = sorted(md_candidates, key=lambda p: p.count("/"))[0]
            md_text = members.get(md_path, b"").decode("utf-8", errors="replace")
            fm_name = fallback_name
            # 用 zip 内技能目录名做兜底名
            dirparts = md_path.split("/")
            if len(dirparts) >= 2:
                fm_name = dirparts[-2]
            parsed = parse_skill_md(md_text, fallback_name=fm_name)
            result["name"] = parsed["name"]
            result["description"] = parsed["description"]
            result["body"] = parsed["body"]
            if parsed.get("error"):
                result["error"] = parsed["error"]
            # scripts / references：相对 SKILL.md 所在目录的 scripts/** references/**
            md_dir = "/".join(md_path.split("/")[:-1])
            prefix_scripts = (md_dir + "/scripts/") if md_dir else "scripts/"
            prefix_refs = (md_dir + "/references/") if md_dir else "references/"
            for path, content in members.items():
                if path == md_path:
                    continue
                if path.startswith(prefix_scripts):
                    rel = path[len(prefix_scripts):]
                    if rel and "/" not in rel:  # 仅取 scripts 直接子文件，避免嵌套过深
                        try:
                            result["scripts"][rel] = content.decode("utf-8", errors="replace")
                        except Exception:
                            pass
                elif path.startswith(prefix_refs):
                    rel = path[len(prefix_refs):]
                    if rel and "/" not in rel:
                        try:
                            result["references"][rel] = content.decode("utf-8", errors="replace")
                        except Exception:
                            pass
        return result
    except Exception as e:
        result["error"] = f"解析 zip 失败: {e}"
        return result


def parse_bytes(data: bytes, filename: str = "", fallback_name: str = "未命名技能") -> Dict[str, Any]:
    """统一入口：字节流自动判定 zip / markdown。返回结构含 scripts/references（md 时为空）。"""
    try:
        if len(data) > MAX_SIZE:
            return {"name": fallback_name, "description": "", "body": "", "scripts": {},
                    "references": {}, "source": "skillmd", "error": "文件过大（>5MB）"}
        if _is_zip_bytes(data):
            return parse_zip(data, fallback_name=fallback_name)
        text = data.decode("utf-8", errors="replace")
        parsed = parse_skill_md(text, fallback_name=filename or fallback_name)
        return {"name": parsed["name"], "description": parsed["description"], "body": parsed["body"],
                "scripts": {}, "references": {}, "source": "skillmd", "error": parsed.get("error")}
    except Exception as e:
        return {"name": fallback_name, "description": "", "body": "", "scripts": {},
                "references": {}, "source": "skillmd", "error": f"解析失败: {e}"}


def parsed_to_skill_data(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """把解析结果转成 skill_store.add 可接收的 payload。"""
    cfg = {
        "name": parsed.get("name", "未命名技能"),
        "description": parsed.get("description", ""),
        "prompt_template": parsed.get("body", ""),
        "executor": "llm",
        "skill_type": "custom",
        "source": "skillmd",
        "skillmd_body": parsed.get("body", ""),
        "scripts": parsed.get("scripts", {}) or {},
        "references": parsed.get("references", {}) or {},
        "parameters": [],
    }
    return {
        "name": cfg["name"],
        "description": cfg["description"],
        "skill_type": "custom",
        "executor": "llm",
        "enabled": True,
        "config": cfg,
    }


def import_skill_package(user_id: int, parsed: Dict[str, Any],
                         is_public: bool = False, is_admin: bool = False) -> Dict[str, Any]:
    """把解析结果作为一条技能写入 mu_skills。

    - 默认私有（owner=user_id）；is_public=True 需 is_admin。
    - 任何异常捕获返回 {success:false, error}。
    """
    try:
        if is_public and not is_admin:
            return {"success": False, "error": "仅管理员可导入公共技能"}
        if not parsed or parsed.get("error"):
            return {"success": False, "error": parsed.get("error") or "解析结果无效"}
        from lobster_mu import skill_store
        data = parsed_to_skill_data(parsed)
        res = skill_store.add(user_id, data, is_public=is_public, is_admin=is_admin)
        if not res.get("success"):
            return res
        skill = res.get("skill") or {}
        # 附带预览结构，便于前端展示
        return {
            "success": True,
            "skill": skill,
            "skill_id": res.get("skill_id"),
            "preview": {
                "name": data["name"],
                "description": data["description"],
                "body_preview": (parsed.get("body", "") or "")[:300],
                "scripts": list((parsed.get("scripts") or {}).keys()),
                "references": list((parsed.get("references") or {}).keys()),
                "source": "skillmd",
            },
        }
    except Exception as e:
        return {"success": False, "error": f"导入失败: {e}"}
