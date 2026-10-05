# -*- coding: utf-8 -*-
"""龙虾Claw 用户命令沙箱执行器抽象层。

- SandboxResult: 统一结果结构
- SandboxExecutor(ABC): 抽象基类
- LocalExecutor: 直通执行（admin 直通 / user_id=0 系统路径）
- DockerExecutor: Docker per-command 容器沙箱（user 角色默认）
- get_executor(user_id): 按角色分派入口

见 spec/user-command-sandbox/spec.md §2。
"""
import abc
import os
import shlex
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from lobster_mu.db import BASE_DIR
from lobster_mu import sandbox_config

_CFG = sandbox_config.config

# 全局 Docker CLI 调用并发上限（§4.3）
_GLOBAL_DOCKER_SEMAPHORE = threading.Semaphore(16)


def _packages_bootstrap(target: str = "/packages") -> str:
    """生成引导代码：把用户依赖目录追加到 sys.path 末尾（仅补充，不覆盖系统包）。

    必须 append 而非前置——否则用户安装的损坏/不兼容包（如坏 numpy）会遮蔽
    系统 site-packages 里的正常包，导致 import 失败。
    """
    return (
        "import sys as _sys\n"
        f"if {target!r} not in _sys.path:\n"
        f"    _sys.path.append({target!r})\n"
    )


def _matplotlib_fmt_shim() -> str:
    """生成 matplotlib 格式字符串容错垫片代码（注入到用户脚本前执行）。

    AI 生成的绘图代码常把完整颜色名写进 fmt，如 plt.plot(x, y, 'gray-')，
    matplotlib 只认单字母颜色简写，会抛 ValueError: 'gray-' is not a valid
    format string。这里在 import matplotlib 后给 Axes.plot 打补丁：把
    'gray-' 这类 <完整颜色名><线型/标记> 自动拆成 color='gray' + fmt='-'，
    仅修正明显的错误写法，不影响正常单字母 fmt（如 'b-'、'go-'）。
    """
    return r'''
# === matplotlib fmt 容错垫片（直接导入并打补丁，确保可靠生效）===
try:
    import re as _re
    import matplotlib.axes as _maxes
    if not getattr(_maxes.Axes, "_lobster_fmt_shim", False):
        import matplotlib.colors as _mcolors
        _cnames = set(_mcolors.CSS4_COLORS) | set(_mcolors.BASE_COLORS) | set(_mcolors.TABLEAU_COLORS)
        _cnames |= {"C%d" % i for i in range(10)}
        # 只处理“完整颜色词”（长度>1），单字母简写（b-/go-）保持原行为
        _cnames = sorted([n for n in _cnames if len(n) > 1], key=len, reverse=True)
        _fmtre = _re.compile(r"^[-\s.*o^v<>1234spPhH+Xx|_,]+$")
        _orig_plot = _maxes.Axes.plot

        def _split_fmt(s):
            for n in _cnames:
                if s.startswith(n):
                    rest = s[len(n):]
                    if rest == "" or _fmtre.match(rest):
                        return n, rest
            return None

        def _lobster_plot(self, *args, **kwargs):
            if "fmt" not in kwargs:
                na = []
                col = None
                for a in args:
                    if col is None and isinstance(a, str):
                        r = _split_fmt(a)
                        if r is not None:
                            n, rest = r
                            col = n
                            if rest:
                                na.append(rest)
                            continue
                    na.append(a)
                args = na
                if col is not None:
                    kwargs.setdefault("color", col)
            return _orig_plot(self, *args, **kwargs)

        _maxes.Axes.plot = _lobster_plot
        _maxes.Axes._lobster_fmt_shim = True

    # --- 中文字体别名：把脚本常引用的 Windows 中文字体名映射到已装的文泉驿 ---
    # 脚本（尤其 AI 生成的）常写 rcParams['font.sans-serif']=['SimHei','Microsoft YaHei',...]，
    # Linux 无这些字体会导致中文变方块。这里把它们别名到预装的 wqy-zenhei，脚本无需改动。
    try:
        import glob as _glob, os as _os
        import matplotlib.font_manager as _fm
        if not getattr(_fm.fontManager, "_lobster_cjk_alias", False):
            _cjk = None
            for _pat in ("/usr/share/fonts/**/wqy*.ttc",
                         "/usr/share/fonts/**/wqy*.ttf",
                         "/usr/share/fonts/**/NotoSansCJK*.otf",
                         "/usr/share/fonts/**/SourceHanSans*.otf"):
                _hits = _glob.glob(_pat, recursive=True)
                if _hits:
                    _cjk = _hits[0]
                    break
            if _cjk and _os.path.exists(_cjk):
                try:
                    _fm.fontManager.addfont(_cjk)
                except Exception:
                    pass
                from matplotlib.font_manager import FontEntry as _FE
                for _alias in ("SimHei", "Microsoft YaHei", "Arial Unicode MS",
                               "SimSun", "KaiTi", "FangSong", "STHeiti", "STSong",
                               "PingFang SC", "Hiragino Sans GB",
                               "Source Han Sans CN", "Source Han Sans SC",
                               "Noto Sans CJK SC", "Noto Sans SC",
                               "WenQuanYi Zen Hei", "WenQuanYi Micro Hei"):
                    _fm.fontManager.ttflist.append(
                        _FE(fname=_cjk, name=_alias))
                # 把文泉驿塞进默认 sans-serif 回退，保证“通用 sans-serif”也能出中文
                try:
                    import matplotlib as _mpl
                    _cur = list(_mpl.rcParams.get("font.sans-serif", []))
                    if "WenQuanYi Zen Hei" not in _cur:
                        _mpl.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei"] + _cur
                except Exception:
                    pass
                _fm.fontManager._lobster_cjk_alias = True
    except Exception:
        pass
except Exception:
    pass
# === 垫片结束 ===
'''


def _sandbox_lib_path() -> str:
    """扫描 packages 下所有含 .so 的目录，转成沙箱内路径，拼为 LD_LIBRARY_PATH。

    解决 numpy/scipy 等把依赖原生库（如 libscipy_openblas64_*.so）放在
    <pkg>.libs/ 下、但其 RPATH 在 --target 布局里找不到的问题。ld.so 只在
    进程启动时读 LD_LIBRARY_PATH，故必须在 docker run 时注入，不能运行时改。
    返回空串表示无 .so。
    """
    try:
        from lobster_mu.script_service import PACKAGES_DIR
    except Exception:
        return ""
    if not os.path.isdir(PACKAGES_DIR):
        return ""
    base = os.path.abspath(PACKAGES_DIR)
    dirs = []
    for root, _sub, files in os.walk(base):
        if any(f.endswith(".so") for f in files):
            rel = os.path.relpath(root, base)
            sp = "/packages" if rel == "." else "/packages/" + rel.replace(os.sep, "/")
            dirs.append(sp)
    # 附带标准库路径，避免覆盖镜像原有的 LD_LIBRARY_PATH 时丢失系统库
    std = "/usr/local/lib:/usr/local/lib64:/usr/lib:/usr/lib64:/lib:/lib64"
    return ":".join(dirs + [std]) if dirs else std


class SandboxUnavailableError(RuntimeError):
    """沙箱后端不可用（Docker 未启动/镜像缺失/WSL2 未就绪）"""


@dataclass
class SandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error: str = ""            # 沙箱级错误（区别于命令级非零返回码）
    timed_out: bool = False
    # 审计用：实际执行方式（exec:direct / exec:sandbox / sandbox:unavailable）
    exec_kind: str = "direct"


class SandboxExecutor(abc.ABC):
    @abc.abstractmethod
    def exec_shell(self, command: str, *, user_id: int, timeout: int = 30,
                   cwd: str = None) -> SandboxResult:
        """执行 shell 命令串（等价现有 execute_shell_command 语义）"""

    @abc.abstractmethod
    def exec_script(self, code: str, *, user_id: int, timeout: int = 60,
                    work_dir: str = None) -> SandboxResult:
        """执行 Python 脚本源码（等价 execute_python_script 的 subprocess 部分）"""


# ============ LocalExecutor（直通） ============

class LocalExecutor(SandboxExecutor):
    """等价现状 tools.py:73-79：subprocess.run(shell=True, cwd=BASE_DIR)。
    仅用于 admin（ADMIN_MODE=direct）与 user_id=0 系统调用路径。"""

    def exec_shell(self, command: str, *, user_id: int, timeout: int = 30,
                   cwd: str = None) -> SandboxResult:
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True,
                timeout=timeout, cwd=cwd or str(BASE_DIR),
            )
            return SandboxResult(
                success=(proc.returncode == 0),
                stdout=proc.stdout.decode("utf-8", errors="replace"),
                stderr=proc.stderr.decode("utf-8", errors="replace"),
                return_code=proc.returncode,
                exec_kind="exec:direct",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(success=False, error=f"命令执行超时（{timeout}秒）",
                                 timed_out=True, exec_kind="exec:direct")
        except Exception as e:
            return SandboxResult(success=False, error=str(e), exec_kind="exec:direct")

    def exec_script(self, code: str, *, user_id: int, timeout: int = 60,
                    work_dir: str = None) -> SandboxResult:
        """脚本直通：写入 work_dir 下临时脚本后 python -B 执行（等价现状语义）。
        调用方（script_service）负责脚本落盘与清理，此处仅执行。"""
        import tempfile
        try:
            os.makedirs(work_dir or str(BASE_DIR), exist_ok=True)
            fd, script_path = tempfile.mkstemp(suffix=".py", dir=work_dir or str(BASE_DIR))
            try:
                # 引导：用户依赖目录追加到 sys.path 末尾（系统包优先，不遮蔽）
                try:
                    from lobster_mu.script_service import PACKAGES_DIR
                    boot = _packages_bootstrap(PACKAGES_DIR)
                except Exception:
                    boot = ""
                boot += _matplotlib_fmt_shim()
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(boot + code)
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                proc = subprocess.run(
                    ["python", "-B", script_path],
                    capture_output=True, timeout=timeout,
                    cwd=work_dir or str(BASE_DIR), env=env,
                )
                return SandboxResult(
                    success=(proc.returncode == 0),
                    stdout=proc.stdout.decode("utf-8", errors="replace"),
                    stderr=proc.stderr.decode("utf-8", errors="replace"),
                    return_code=proc.returncode,
                    exec_kind="exec:direct",
                )
            finally:
                try:
                    if os.path.exists(script_path):
                        os.unlink(script_path)
                except OSError:
                    pass
        except subprocess.TimeoutExpired:
            return SandboxResult(success=False, error=f"脚本执行超时（{timeout}秒）",
                                 timed_out=True, exec_kind="exec:direct")
        except Exception as e:
            return SandboxResult(success=False, error=str(e), exec_kind="exec:direct")


# ============ DockerExecutor（沙箱） ============

class DockerExecutor(SandboxExecutor):
    """Docker per-command 容器沙箱（§2.4）。
    调用 docker CLI，不引入 docker-py SDK。"""

    _docker_ok_cache = None      # (bool, timestamp)
    _docker_ok_lock = threading.Lock()
    _PROBE_TTL = 30              # 秒
    _per_user_semaphores = {}
    _sem_lock = threading.Lock()
    _consecutive_failures = 0

    # ---- Docker 探测（TTL 缓存） ----
    def _docker_available(self) -> bool:
        with DockerExecutor._docker_ok_lock:
            cache = DockerExecutor._docker_ok_cache
            if cache and (time.time() - cache[1]) < DockerExecutor._PROBE_TTL:
                return cache[0]
        try:
            proc = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=10,
            )
            ok = (proc.returncode == 0)
        except Exception:
            ok = False
        with DockerExecutor._docker_ok_lock:
            DockerExecutor._docker_ok_cache = (ok, time.time())
            # 连续失败触发缓存失效（§5.3）
            if not ok:
                DockerExecutor._consecutive_failures += 1
                if DockerExecutor._consecutive_failures >= 5:
                    DockerExecutor._docker_ok_cache = None
                    DockerExecutor._consecutive_failures = 0
            else:
                DockerExecutor._consecutive_failures = 0
        return ok

    def _invalidate_probe(self):
        with DockerExecutor._docker_ok_lock:
            DockerExecutor._docker_ok_cache = None

    # ---- 每用户信号量（§2.4 并发限制） ----
    def _get_user_semaphore(self, user_id: int) -> threading.Semaphore:
        with DockerExecutor._sem_lock:
            sem = DockerExecutor._per_user_semaphores.get(user_id)
            if sem is None:
                sem = threading.Semaphore(max(1, _CFG.per_user_concurrency))
                DockerExecutor._per_user_semaphores[user_id] = sem
            return sem

    # ---- 沙箱不可用处置（§5.2） ----
    def _handle_unavailable(self, user_id: int, reason: str) -> SandboxResult:
        # 写审计（延迟 import 避免循环）
        try:
            from lobster_mu.tools import log_operation
            log_operation(user_id, "sandbox:unavailable",
                          detail=f"user_id={user_id}", success=False,
                          error=reason)
        except Exception:
            pass
        if _CFG.fallback == "warn":
            # 回退直通执行 + 告警（仅 dev 允许，实际执行由 exec_shell/exec_script 处理）
            import logging
            logging.getLogger(__name__).warning(
                f"[沙箱] fallback=warn：Docker 不可用（{reason}），user_id={user_id} 回退直通执行")
        # deny：拒绝执行
        return SandboxResult(
            success=False,
            error=f"命令沙箱不可用（{reason}），user 角色禁止直接执行。请联系管理员。",
            exec_kind="sandbox:unavailable",
        )

    # ---- 挂载参数构建（§4.1） ----
    def _host_path(self, path: str) -> str:
        """Docker-out-of-Docker 路径翻译：容器内 BASE_DIR 下的路径映射到宿主机。
        未配置 host_app_dir 时原样返回（直跑宿主机场景）。"""
        host_app = (_CFG.host_app_dir or "").rstrip("/")
        if not host_app:
            return path
        base = str(BASE_DIR).rstrip("/")
        ap = os.path.abspath(path)
        if ap == base or ap.startswith(base + os.sep):
            return host_app + ap[len(base):]
        return path

    def _build_mounts(self, user_id: int, work_dir: Optional[str]) -> list:
        from lobster_mu.paths import files_dir
        mounts = []
        # /files (rw)：用户产物目录
        try:
            fdir = self._host_path(files_dir(user_id))
            mounts.append(f"--mount=type=bind,source={fdir},target=/files")
        except Exception:
            pass
        # /data (ro)：数据目录只读
        data_dir = os.path.join(BASE_DIR, "data")
        if os.path.isdir(data_dir):
            mounts.append(f"--mount=type=bind,source={self._host_path(data_dir)},target=/data,ro")
        # /packages (ro)：第三方包只读（P7 决议）
        try:
            from lobster_mu.script_service import PACKAGES_DIR
            if os.path.isdir(PACKAGES_DIR):
                mounts.append(f"--mount=type=bind,source={self._host_path(PACKAGES_DIR)},target=/packages,ro")
        except Exception:
            pass
        # work_dir 额外挂载（脚本执行时若 work_dir != files_dir）
        if work_dir and os.path.isdir(work_dir):
            wd = os.path.abspath(work_dir)
            if wd != os.path.abspath(files_dir(user_id)):
                mounts.append(f"--mount=type=bind,source={self._host_path(wd)},target=/work")
        return mounts

    def _run_docker(self, args: list, timeout: int, user_id: int,
                    container_name: str) -> SandboxResult:
        """执行 docker CLI，超时 kill 容器。args 为 docker run 之后的参数列表。"""
        cmd = ["docker"] + args
        sem = _GLOBAL_DOCKER_SEMAPHORE
        user_sem = self._get_user_semaphore(user_id)
        try:
            with sem, user_sem:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                try:
                    stdout, stderr = proc.communicate(timeout=timeout)
                    return SandboxResult(
                        success=(proc.returncode == 0),
                        stdout=stdout.decode("utf-8", errors="replace"),
                        stderr=stderr.decode("utf-8", errors="replace"),
                        return_code=proc.returncode,
                        exec_kind="exec:sandbox",
                    )
                except subprocess.TimeoutExpired:
                    # 宿主侧超时：kill 容器（双保险 §P8）
                    try:
                        subprocess.run(["docker", "kill", container_name],
                                       capture_output=True, timeout=5)
                    except Exception:
                        pass
                    # 强制终止当前进程
                    try:
                        proc.kill()
                        proc.communicate(timeout=5)
                    except Exception:
                        pass
                    return SandboxResult(
                        success=False,
                        error=f"命令执行超时（{timeout}秒）",
                        timed_out=True,
                        exec_kind="exec:sandbox",
                    )
        except FileNotFoundError:
            return self._handle_unavailable(user_id, "docker-not-running")
        except Exception as e:
            # 区分镜像缺失
            err_str = str(e)
            if "No such image" in err_str or "not found" in err_str.lower():
                self._invalidate_probe()
                return self._handle_unavailable(user_id, "image-missing")
            return SandboxResult(success=False, error=err_str, exec_kind="exec:sandbox")

    def _base_args(self, user_id: int, mounts: list) -> list:
        """构建 docker run 公共参数（§2.4 容器参数模板）"""
        ts8 = f"{int(time.time()) % 100000000:08x}"
        container_name = f"lobster-sb-{user_id}-{ts8}"
        # 注意：不加 --interactive。命令以 sh -c "..." 形式执行，无需 stdin 交互；
        # 非 TTY 下 --interactive 会导致 docker 挂起等待 stdin EOF 才执行命令。
        args = [
            "run", "--rm",
            "--name", container_name,
            "--hostname", f"lobster-sb-{user_id}",
            "--workdir", "/work",
        ]
        args.extend(mounts)
        # 资源限制
        args.extend(["--memory", _CFG.mem_limit, "--memory-swap", _CFG.mem_limit])
        args.extend(["--cpus", str(_CFG.cpu_limit)])
        args.extend(["--pids-limit", str(_CFG.pids_limit)])
        # 网络
        args.extend(["--network", _CFG.network])
        # 安全
        args.extend(["--cap-drop", "ALL", "--security-opt", "no-new-privileges"])
        # 非 root 用户
        args.extend(["--user", "lobster"])
        # 注意：不设置 PYTHONPATH=/packages！PYTHONPATH 会前置到 sys.path，
        # 导致用户安装的（可能损坏/不兼容的）包遮蔽系统 site-packages 里的正常包
        # （典型：用户装了坏 numpy，import numpy 拿到坏的 → C 扩展加载失败）。
        # 用户依赖改为在执行代码前以 sys.path.append 注入（末尾，仅补充系统包），
        # 见 exec_script / exec_shell 的 _packages_bootstrap。
        args.extend(["--env", "PYTHONIOENCODING=utf-8", "--env", "PYTHONUTF8=1"])
        # 注入 LD_LIBRARY_PATH：让 numpy/scipy 等放在 <pkg>.libs/ 下的原生 .so
        # （如 libscipy_openblas64_*.so）能被动态链接器找到。ld.so 仅在进程启动
        # 时读取，必须在此注入，不能运行时改环境变量。
        lib_path = _sandbox_lib_path()
        if lib_path:
            args.extend(["--env", f"LD_LIBRARY_PATH={lib_path}"])
        # 停止超时
        args.extend(["--stop-timeout", "3"])
        # 镜像
        args.append(_CFG.image)
        # 记录容器名供超时 kill
        self._last_container = container_name
        return args

    def exec_shell(self, command: str, *, user_id: int, timeout: int = 30,
                   cwd: str = None) -> SandboxResult:
        if not _CFG.enabled:
            return LocalExecutor().exec_shell(command, user_id=user_id, timeout=timeout, cwd=cwd)
        if not self._docker_available():
            if _CFG.fallback == "warn":
                import logging
                logging.getLogger(__name__).warning(
                    f"[沙箱] fallback=warn：Docker 不可用，user_id={user_id} 回退直通执行")
                return LocalExecutor().exec_shell(command, user_id=user_id, timeout=timeout, cwd=cwd)
            return self._handle_unavailable(user_id, "docker-not-running")

        mounts = self._build_mounts(user_id, cwd)
        args = self._base_args(user_id, mounts)
        # 超时 kill 需要容器名（_base_args 已设置 self._last_container）
        args.extend(["sh", "-c", command])
        timeout = min(timeout, max(timeout, _CFG.timeout)) if timeout else _CFG.timeout
        return self._run_docker(args, timeout, user_id, self._last_container)

    def exec_script(self, code: str, *, user_id: int, timeout: int = 60,
                    work_dir: str = None) -> SandboxResult:
        """脚本沙箱：docker run 一步执行 python3 -B -c '<code>'（§2.4）。
        挂载含 /files(rw) + /packages(ro) + /data(ro)，PYTHONPATH=/packages。
        与 exec_shell 的 sh -c 模式一致，避免 create/exec 的 running 状态问题。"""
        if not _CFG.enabled:
            return LocalExecutor().exec_script(code, user_id=user_id, timeout=timeout, work_dir=work_dir)
        if not self._docker_available():
            if _CFG.fallback == "warn":
                import logging
                logging.getLogger(__name__).warning(
                    f"[沙箱] fallback=warn：Docker 不可用，user_id={user_id} 脚本回退直通执行")
                return LocalExecutor().exec_script(code, user_id=user_id, timeout=timeout, work_dir=work_dir)
            return self._handle_unavailable(user_id, "docker-not-running")

        from lobster_mu.paths import files_dir
        mounts = self._build_mounts(user_id, work_dir)
        args = self._base_args(user_id, mounts)

        # 脚本通过 python3 -B -c 传入（与 exec_shell 的 sh -c 模式一致）
        # 前置引导：把 /packages 追加到 sys.path 末尾（系统包优先，用户包仅补充）。
        import shlex
        script_cmd = "python3 -B -c " + shlex.quote(_packages_bootstrap("/packages") + _matplotlib_fmt_shim() + code)
        args.extend(["sh", "-c", script_cmd])
        # 超时 kill 需要容器名（_base_args 已设置 self._last_container）
        timeout = min(timeout, max(timeout, _CFG.timeout)) if timeout else _CFG.timeout
        result = self._run_docker(args, timeout, user_id, self._last_container)
        if result.exec_kind != "script:sandbox":
            result.exec_kind = "script:sandbox"
        return result


# ============ get_executor（角色判定入口） ============

_local_executor = LocalExecutor()
_docker_executor = None
_executor_lock = threading.Lock()


def get_executor(user_id: int) -> SandboxExecutor:
    """按角色分派执行器（§2.2）：
    1. user_id=0（系统/未知）→ LocalExecutor（直通 + 审计告警）
    2. role=admin 且 admin_mode=direct → LocalExecutor
    3. 其余 → DockerExecutor
    """
    global _docker_executor

    # user_id=0：系统调用路径，直通（§2.3 P5）
    if not user_id or user_id <= 0:
        try:
            from lobster_mu.tools import log_operation
            log_operation(0, "exec:direct", detail="user_id=0 系统调用直通", success=True)
        except Exception:
            pass
        return _local_executor

    # 查角色
    role = "user"
    try:
        from lobster_mu import user_store
        row = user_store.get_by_id(user_id)
        if row:
            role = row["role"] or "user"
    except Exception:
        role = "user"

    # admin + direct → 直通
    if role == "admin" and _CFG.admin_mode == "direct":
        return _local_executor

    # 其余 → Docker
    if _CFG.enabled and _CFG.mode == "docker":
        with _executor_lock:
            if _docker_executor is None:
                _docker_executor = DockerExecutor()
            return _docker_executor
    # 沙箱禁用或 mode 非 docker → 直通
    return _local_executor


def reset_cache():
    """重置执行器缓存 + 刷新 _CFG 配置快照（测试用，配合 sandbox_config.reload）。

    _CFG 是模块级快照，配置 reload 后需同步刷新，否则 get_executor 读到旧值。"""
    global _docker_executor, _CFG
    with _executor_lock:
        _docker_executor = None
    _CFG = sandbox_config.config
    DockerExecutor._docker_ok_cache = None
    DockerExecutor._consecutive_failures = 0


def install_dependency_in_sandbox(package_name: str, timeout: int = 600):
    """在沙箱镜像内（其自带 python3 与执行环境 ABI 一致）安装依赖到共享 /packages。

    为何必须在沙箱内装：主容器是 python3.11，沙箱镜像是 python3.12。
    若用主容器 pip 装带 C 扩展的包（numpy/pandas/torch…），得到的 .so 是
    cpython-311，在沙箱 3.12 里 import 必崩（ABI 不匹配）。
    故安装也走沙箱镜像的 python3，装出的二进制与执行环境一致。

    返回 (ok: bool, output: str)。docker 不可用时返回 (False, 原因)。
    """
    if not _CFG.enabled or _CFG.mode != "docker":
        return False, "沙箱未启用（mode!=docker），无法在沙箱内安装"
    exe = DockerExecutor()
    if not exe._docker_available():
        return False, "docker 不可用，无法在沙箱内安装"

    from lobster_mu.script_service import PACKAGES_DIR
    host_pkg = exe._host_path(PACKAGES_DIR)

    mirror_sources = [
        ('https://pypi.tuna.tsinghua.edu.cn/simple', 'pypi.tuna.tsinghua.edu.cn'),
        ('https://mirrors.aliyun.com/pypi/simple/', 'mirrors.aliyun.com'),
        ('https://pypi.mirrors.ustc.edu.cn/simple/', 'pypi.mirrors.ustc.edu.cn'),
        ('https://pypi.douban.com/simple/', 'pypi.douban.com'),
    ]
    last_out = ""
    for index_url, trusted_host in mirror_sources:
        pip_cmd = (
            f"python3 -m pip install --target /packages --no-warn-script-location "
            f"--index-url {index_url} --trusted-host {trusted_host} {shlex.quote(package_name)}"
        )
        ts8 = f"{int(time.time()) % 100000000:08x}"
        cname = f"lobster-pip-{ts8}"
        args = [
            "run", "--rm", "--name", cname,
            "--network", "host",                 # 装包需联网
            "--user", "root",                     # 写 /packages 需权限
            f"--mount=type=bind,source={host_pkg},target=/packages",
            _CFG.image, "sh", "-c", pip_cmd,
        ]
        try:
            proc = subprocess.run(
                ["docker"] + args, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
            last_out = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode == 0:
                return True, last_out
        except subprocess.TimeoutExpired:
            last_out = f"镜像源 {index_url} 安装超时"
            continue
        except FileNotFoundError:
            return False, "docker CLI 不存在"
    return False, last_out or "所有镜像源安装失败"
