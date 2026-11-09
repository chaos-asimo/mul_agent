# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 用户文件目录规范与归属校验（防路径穿越）"""
import os
import re
import secrets
from datetime import datetime

from lobster_mu.db import BASE_DIR

STATIC_DIR = os.path.join(BASE_DIR, "web", "static")

# 工具类端点（read/write/edit/list/exec）的只读附加根：data/ 只读
USER_READ_ONLY_EXTRA = os.path.join(BASE_DIR, "data")

_UNSAFE_NAME = re.compile(r"[^\w.\-\u4e00-\u9fff]+")


def uploads_dir(user_id: int) -> str:
    """用户上传目录：web/static/uploads/claw/{uid}/"""
    d = os.path.join(STATIC_DIR, "uploads", "claw", str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def files_dir(user_id: int) -> str:
    """脚本生成文件/PDF 产物目录：web/static/lobster-claw-files/{uid}/"""
    d = os.path.join(STATIC_DIR, "lobster-claw-files", str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def mu_files_dir(user_id: int) -> str:
    """工具读写白名单根：web/static/mu-files/{uid}/"""
    d = os.path.join(STATIC_DIR, "mu-files", str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def gen_filename(original_name: str) -> str:
    """生成 {时间戳}_{随机hex}{扩展名} 文件名（保留原扩展，限制不可枚举）"""
    ext = os.path.splitext(original_name or "")[1][:16]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{secrets.token_hex(4)}{ext}"


def safe_filename(name: str) -> str:
    """清洗文件名（去路径分隔符与非法字符）"""
    name = os.path.basename(name or "file")
    cleaned = _UNSAFE_NAME.sub("_", name).strip("._") or "file"
    return cleaned[:120]


def _inside(user_root: str, target: str) -> bool:
    user_root = os.path.abspath(user_root)
    target = os.path.abspath(target)
    return target == user_root or target.startswith(user_root + os.sep)


def is_user_path(user_id: int, path: str, write: bool = False) -> bool:
    """校验路径归属：写操作必须在该用户目录内；读操作额外允许 data/ 只读"""
    resolved = os.path.abspath(os.path.join(str(BASE_DIR), path)) \
        if not os.path.isabs(path) else os.path.abspath(path)
    user_roots = [
        mu_files_dir(user_id),
        uploads_dir(user_id),
        files_dir(user_id),
    ]
    if any(_inside(root, resolved) for root in user_roots):
        return True
    if not write and _inside(USER_READ_ONLY_EXTRA, resolved):
        return True
    return False


def _is_clean_relative(path: str) -> bool:
    """干净相对路径：无盘符、不以分隔符开头、不含 ..（可直接映射到用户目录）"""
    if not path or os.path.isabs(path) or path.startswith(("/", "\\")):
        return False
    if re.match(r"^[A-Za-z]:", path):
        return False
    parts = re.split(r"[\\/]+", path)
    return ".." not in parts


def resolve_user_path(user_id: int, path: str, write: bool = False) -> str:
    """解析并校验用户路径，非法则抛 ValueError。
    干净相对路径直接映射到该用户的 mu-files 目录；其余路径解析后校验归属。"""
    if _is_clean_relative(path):
        return os.path.abspath(os.path.join(mu_files_dir(user_id), path))
    resolved = os.path.abspath(os.path.join(str(BASE_DIR), path)) \
        if not os.path.isabs(path) else os.path.abspath(path)
    if not is_user_path(user_id, resolved, write=write):
        raise ValueError(f"路径越权访问: {path}")
    return resolved
