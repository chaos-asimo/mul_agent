# -*- coding: utf-8 -*-
"""龙虾Claw 用户命令沙箱配置层。

统一前缀 LOBSTER_SANDBOX_*，从环境变量解析，进程启动时固化。
非法枚举值抛 SandboxConfigError 使启动失败（防拼写错误静默直通）。
见 spec/user-command-sandbox/spec.md §3。
"""
import os
from dataclasses import dataclass, field
from typing import Optional


class SandboxConfigError(Exception):
    """沙箱配置错误（非法枚举值等），应在启动时拒绝服务"""


@dataclass
class SandboxConfig:
    # 总开关：false 时所有角色直通（等价现状，仅限纯 dev 显式关闭）
    enabled: bool = True
    # 后端类型：首期唯一实现 docker；firejail/disabled 预留
    mode: str = "docker"
    # 沙箱镜像名
    image: str = "lobster-claw-sandbox:local"
    # 后端不可用处置：deny（默认，user 拒绝）/ warn（回退直通+告警，仅 dev）
    fallback: str = "deny"
    # admin 角色行为：direct（默认直通）/ sandbox（也走沙箱）
    admin_mode: str = "direct"
    # 命令执行默认超时秒数
    timeout: int = 30
    # 容器资源限制
    mem_limit: str = "512m"
    cpu_limit: float = 1.0
    pids_limit: int = 128
    # 网络：none（默认断网）/ sandbox-net
    network: str = "none"
    # 每 user_id 并发容器数上限
    per_user_concurrency: int = 4
    # 长驻模式空闲超时（首期忽略）
    idle_timeout: int = 600
    # /work 的宿主侧映射
    host_cwd: str = ""
    # Docker-out-of-Docker：容器内 BASE_DIR 对应的宿主机绝对路径。
    # 留空表示不做翻译（直跑在宿主机时）。容器化部署时需设为宿主项目根，
    # 使 --mount source= 指向宿主机真实路径。
    host_app_dir: str = ""

    # 运行时自检产物（非配置项）
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


_VALID_MODE = {"docker", "firejail", "disabled"}
_VALID_FALLBACK = {"deny", "warn"}
_VALID_ADMIN_MODE = {"direct", "sandbox"}
_VALID_NETWORK = {"none", "sandbox-net"}


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    val = raw.strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    raise SandboxConfigError(f"{name} 值非法: {raw}（应为 true/false）")


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise SandboxConfigError(f"{name} 值非法: {raw}（应为整数）")


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        raise SandboxConfigError(f"{name} 值非法: {raw}（应为浮点数）")


def _get_enum(name: str, default: str, valid: set, cfg: SandboxConfig) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    val = raw.strip().lower()
    if val not in valid:
        cfg.errors.append(f"{name} 值非法: {val}（合法值: {sorted(valid)}）")
        raise SandboxConfigError(f"{name} 值非法: {val}（合法值: {sorted(valid)}）")
    return val


def _get_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def load() -> SandboxConfig:
    """解析环境变量，返回配置单例。非法值抛 SandboxConfigError。"""
    cfg = SandboxConfig()
    cfg.enabled = _get_bool("LOBSTER_SANDBOX_ENABLED", True)
    cfg.mode = _get_enum("LOBSTER_SANDBOX_MODE", "docker", _VALID_MODE, cfg)
    cfg.image = _get_str("LOBSTER_SANDBOX_IMAGE", "lobster-claw-sandbox:local")
    cfg.fallback = _get_enum("LOBSTER_SANDBOX_FALLBACK", "deny", _VALID_FALLBACK, cfg)
    cfg.admin_mode = _get_enum("LOBSTER_SANDBOX_ADMIN_MODE", "direct", _VALID_ADMIN_MODE, cfg)
    cfg.timeout = _get_int("LOBSTER_SANDBOX_TIMEOUT", 30)
    cfg.mem_limit = _get_str("LOBSTER_SANDBOX_MEM_LIMIT", "512m")
    cfg.cpu_limit = _get_float("LOBSTER_SANDBOX_CPU_LIMIT", 1.0)
    cfg.pids_limit = _get_int("LOBSTER_SANDBOX_PIDS_LIMIT", 128)
    cfg.network = _get_enum("LOBSTER_SANDBOX_NETWORK", "none", _VALID_NETWORK, cfg)
    cfg.per_user_concurrency = _get_int("LOBSTER_SANDBOX_PER_USER_CONCURRENCY", 4)
    cfg.idle_timeout = _get_int("LOBSTER_SANDBOX_IDLE_TIMEOUT", 600)
    cfg.host_app_dir = _get_str("LOBSTER_SANDBOX_HOST_APP_DIR", "")

    # host_cwd 默认取 BASE_DIR（延迟 import 避免循环）
    try:
        from lobster_mu.db import BASE_DIR
        cfg.host_cwd = _get_str("LOBSTER_SANDBOX_HOST_CWD", BASE_DIR)
    except Exception:
        cfg.host_cwd = _get_str("LOBSTER_SANDBOX_HOST_CWD", os.getcwd())

    return cfg


# 模块级单例（进程启动时固化）
config: SandboxConfig = load()


def reload() -> SandboxConfig:
    """重新解析环境变量（配置变更需重启，本函数仅供测试/热加载）"""
    global config
    config = load()
    return config
