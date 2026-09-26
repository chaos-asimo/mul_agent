# 龙虾Claw v3 用户命令沙箱规范

## 0. 现状与目标

### 0.1 现状（基于真实代码核实）

| 执行路径 | 文件:行号 | 现状问题 |
|---|---|---|
| Agent 工具 `exec` | `lobster_mu/tools.py:490-491`（`execute_tool_call` → `exec_cmd`） | `exec_cmd` 黑名单+首 token 白名单（`tools.py:92-117`）后调 `execute_shell_command`（`tools.py:70-89`），**`subprocess.run(command, shell=True, cwd=BASE_DIR)` 直接落宿主机**，且 `user_id` 未传递到执行层 |
| HTTP 端点 `/exec` | `web/routes/lobster_mu.py:677-706` | `mu_exec` 只过 `is_command_safe` 黑名单（`tools.py:62-67`），`_async_shell` 用 `asyncio.create_subprocess_shell(shell=True, cwd=项目根)` 直执行，**无白名单、无角色判定** |
| Python 脚本执行 | `lobster_mu/script_service.py:580-616` | `execute_python_script` 用 `subprocess.run(['python','-B',script_path], cwd=用户产物目录)` 直执行。**Python 代码可 `os.system`/`subprocess` 任意逃逸，黑名单完全无效** |
| 定时任务 command | `lobster_mu/cron_runner.py:187-207` | `_execute_command_task` 只过黑名单后调 `tools.execute_shell_command`，同样落宿主机 |
| 角色判定缺口 | `lobster_mu/security.py:39-42` | `require_admin` 仅用于 `/admin/*`、`/feishu/*`，**`/exec`、`/script/execute` 对所有登录角色开放且行为一致** |
| 路径限制缺口 | `lobster_mu/paths.py:85-94` | `resolve_user_path` 只约束文件类工具（`tools.py:122-216`），**不约束 shell 命令** |

核心矛盾：**user 角色（`users.role='user'`，见 `lobster_mu/user_store.py:71`）的命令执行面与 admin 完全等价**，黑名单可被 shell 注入（`$(...)`、反引号、`;`、`|`）或 Python 脚本内 `subprocess` 绕过。

### 0.2 目标

- user 角色的命令/脚本不在宿主机（或主容器）直接执行，而是在隔离沙箱中执行。
- admin 角色保留现有直接执行能力（默认行为不变，见 §8 P1）。
- 兼容三种部署形态：本地 Windows 开发（直接 `python web_server.py`）、Docker 容器部署（Linux）、生产 Linux 主机。
- 沙箱不可用时行为明确（§5），不静默降级为无隔离执行。

---

## 1. 方案选型

### 1.1 候选方案对比

| 维度 | A. Docker per-command 容器 | B. Linux namespace（bwrap/firejail） | C. gVisor / Kata Containers | D. Windows 专用容器/虚拟化 | E. chroot + seccomp（纯 Python） |
|---|---|---|---|---|---|
| 隔离强度 | 强（完整容器） | 中-强（PID/mount/net ns，无内核隔离） | 极强（用户态内核） | 强（Hyper-V）/中（WSL2） | 中（seccomp 可绕过场景多） |
| 跨平台（Win 开发） | 需 Docker Desktop（WSL2 后端） | ❌ 不可用（需 Linux 内核 + unprivileged userns） | ❌ 不可用（仅 Linux） | ⚠️ 需 Hyper-V/WSL2，普通 Windows 开发机常不可用 | ⚠️ seccomp 不支持 Windows，chroot 不可用 |
| 单命令开销 | ~100-500ms（`docker run --rm`，镜像已 pull 后） | ~10ms | ~500ms-1s（runsc 启动） | ~1-3s（Hyper-V VM） | ~5ms |
| 实现复杂度 | 低（subprocess 调 docker CLI） | 中（按发行版处理 userns 配置、AppArmor 策略） | 高（dockerd 支持 runsc、镜像兼容验证） | 高（多套逻辑、VM 生命周期） | 高（Python 手写 seccomp 绑定，维护成本大） |
| 命令兼容性（`tools.py:28-35` 白名单） | 取决于沙箱镜像内预装的二进制；**基础镜像需预装 coreutils** | 继承宿主 PATH，兼容性好（但能看到宿主文件系统，需 ns 隐藏） | 同 Docker | 容器内工具链受限（Windows 容器无 Linux 二进制） | 同宿主，兼容性最好 |
| 依赖 | Docker Engine / Docker Desktop | Linux 内核 ≥4.18 + bwrap/firejail 二进制 | gvisor (runsc) + 修改 Docker daemon | Windows + WSL2/Hyper-V | 无外部依赖（但 Windows 上不可行） |
| 嵌套问题 | 主容器内跑 Docker 需 `--privileged` 或 socket 挂载（有逃逸风险，见 §8 P3） | 在 Docker 容器内需要 `--cap-add SYS_ADMIN` 或 unprivileged userns 放行 | 同 Docker | 同 Docker | 无 |

### 1.2 推荐方案

**主方案：A（Docker per-command 容器）+ 按平台分派的 `SandboxExecutor` 抽象**，理由：

1. **现实约束决定**：本项目生产形态是 Docker 容器（`docker-compose.yml` 单服务 `mul-agent`，镜像 `python:3.11-slim-bookworm`）和 Linux 主机；本地开发是 Windows（直接 `python web_server.py`，见 `web_server.py` 入口）。唯一同时覆盖 Linux 部署 + Windows 开发且隔离强度达标的技术是 Docker（Linux 下走 Docker Engine，Windows 下走 Docker Desktop/WSL2）。
2. **隔离强度与开销平衡**：bwrap（B）虽轻，但 Windows 不可用，意味着本地开发要么无沙箱、要么再维护一套逻辑，违背"一套抽象两种后端"的原则。gVisor（C）隔离更强但启动慢、镜像兼容验证成本高，对"echo/cat/grep 级别的命令"是过度设计。
3. **命令兼容性可控**：白名单命令（`tools.py:28-35`）全部是 coreutils 标准工具，沙箱镜像基于 `debian:bookworm-slim`（与运行时镜像 `python:3.11-slim-bookworm` 同系）预装 `coreutils + procps + iproute2 + python3` 即可全量覆盖；脚本执行需要 `python3`（`script_service.py:611` 用 `python`，沙箱镜像内 `python3 → python` 软链）。
4. **复用现有部署资产**：沙箱镜像可随项目一起构建（新增 `sandbox/Dockerfile`），与主镜像同源、同基础镜像，避免 gVisor 之类的额外基础设施。

**备选/降级**（见 §5）：
- Linux 主机无 Docker 时：可选 `SANDBOX_MODE=firejail`（B 方案），作为**运维显式配置项**而非默认，不纳入首期实现范围（首期只实现 docker 后端 + disabled 两态）。
- Windows 无 Docker Desktop 时：user 角色命令**拒绝执行**并返回明确错误（`SANDBOX_FALLBACK=deny`，默认值）。

**明确排除**：
- E（chroot+seccomp 纯 Python）：Windows 不可行，且 seccomp 过滤规则维护成本高、易留逃逸面，不如 Docker 默认隔离模型成熟。
- D（Windows 专用容器）：Hyper-V 要求高、WSL2 本质上是 Linux 虚拟机（又回到 A 的镜像逻辑），单独立项价值低。

### 1.3 命令兼容性保障（白名单对齐）

沙箱镜像必须预装 `tools.py:28-35` `ALLOWED_COMMANDS` 全量对应的二进制，构建期断言：

```dockerfile
# sandbox/Dockerfile（构建期检查，缺失则构建失败）
RUN for c in echo ls cat find grep date whoami hostname uname ping ps tree pwd head tail wc cut split join sort; do \
      command -v $c >/dev/null || (echo "missing: $c" && exit 1); done
```

注：`dir/type/ver/ipconfig/tasklist/cls`（Windows 系）与 `tracert/nslookup/netstat/ifconfig/more/less/paste`（Linux 下部分缺失）在 Linux 沙箱内不存在。规范定义：**沙箱执行路径内，白名单以"沙箱镜像实际可用命令"为准**；`exec_cmd`（`tools.py:96-100`）的白名单校验保留不变，命令不存在时由沙箱返回非零 return_code + `stderr: command not found`，对用户表现为命令失败而非安全绕过。

---

## 2. 架构设计

### 2.1 总体结构

```
                    ┌─────────────────────────────────────────────┐
                    │  调用方（均已知 user_id）                      │
                    │  • tools.execute_tool_call (tools.py:484)    │
                    │  • routes.mu_exec (lobster_mu.py:677)        │
                    │  • script_service.execute_python_script (580)│
                    │  • cron_runner._execute_command_task (187)   │
                    └───────────────┬─────────────────────────────┘
                                    │ execute(command/script, user_id, timeout)
                                    ▼
                    ┌─────────────────────────────────────────────┐
                    │  lobster_mu/sandbox.py（新增）                │
                    │  get_executor() → SandboxExecutor            │
                    │  判定：role == 'admin' 且 ADMIN_DIRECT_EXEC   │
                    │        → LocalExecutor（原路）                │
                    │        → DockerExecutor（user 角色，默认）     │
                    │  Docker 不可用 → 按 SANDBOX_FALLBACK 处置     │
                    └───────────────┬─────────────────────────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                              ▼
            LocalExecutor                    DockerExecutor
        subprocess.run(shell=True)       docker run --rm
        （现有 tools.py:73-79 逻辑）        sandbox:{uid} 容器
                                           挂载 per-user 目录
                                           cpus/mem/pids/net 限制
                                           超时 kill
```

### 2.2 接口设计（`lobster_mu/sandbox.py`）

```python
class SandboxUnavailableError(RuntimeError):
    """沙箱后端不可用（Docker 未启动/镜像缺失/WSL2 未就绪）"""

class SandboxResult:
    success: bool
    stdout: str          # utf-8 解码，errors='replace'（与 tools.py:82 一致）
    stderr: str
    return_code: int
    error: str = ''      # 沙箱级错误（区别于命令级非零返回码）
    timed_out: bool = False

class SandboxExecutor(abc.ABC):
    @abc.abstractmethod
    def exec_shell(self, command: str, *, user_id: int, timeout: int = 30,
                   cwd: str = None) -> SandboxResult:
        """执行 shell 命令串（等价现有 execute_shell_command 语义）"""

    @abc.abstractmethod
    def exec_script(self, code: str, *, user_id: int, timeout: int = 60,
                    work_dir: str = None) -> SandboxResult:
        """执行 Python 脚本源码（等价 execute_python_script 的 subprocess 部分）"""
```

**角色判定与执行器选择**（`get_executor(user_id)` 内部）：

1. `role = user_store.get_by_id(user_id)["role"]`（`user_store.py:58-64`）。
2. `role == 'admin'` 且 `SANDBOX_ADMIN_MODE == 'direct'`（默认）→ `LocalExecutor`（保持现有行为，admin 不沙箱化）。
3. 其余 → `DockerExecutor`。
4. `DockerExecutor` 初始化时探测 Docker（`docker info`，缓存结果 + TTL 30s 重探）；不可用时按 §5 处置。

### 2.3 嵌入点与调用链改造

| 嵌入点 | 现状 | 改造后 |
|---|---|---|
| `tools.py:491` `execute_tool_call` exec 分支 | `exec_cmd(command)`（无 user_id） | `exec_cmd(command, user_id)`；`exec_cmd` 内部把 `execute_shell_command(command, timeout)` 替换为 `get_executor(user_id).exec_shell(command, user_id=user_id, timeout=timeout)`，白名单/黑名单校验**保留不变**（沙箱是纵深防御第二层，不替代第一层） |
| `tools.py:70-89` `execute_shell_command` | 直接 `subprocess.run` | 签名增加可选 `user_id: int = 0`；`user_id=0`（未知/系统调用）时按 admin 直通处理并记录审计告警（见 §8 P5）。现有不传 user_id 的调用方（`cron_runner.py:195-196`）改为显式传入 `task["user_id"]`（`cron_runner.py:82` 已有） |
| `lobster_mu.py:677-706` `mu_exec` + `_async_shell` | `_async_shell` 异步直执行 | `mu_exec` 改为调用 `tools.exec_cmd(body.command, user["id"])`（**复用同一套白名单**，修复现状"HTTP /exec 无白名单"缺口），异步性通过 `run_in_executor` 包装同步的 `SandboxResult` 接口实现；删除 `_async_shell`（`lobster_mu.py:688-706`） |
| `script_service.py:580-616` `execute_python_script` | `subprocess.run(['python','-B',script_path])` | 保留"脚本落盘到 `files_dir(user_id)`（`paths.py:25-29`）"逻辑不变；把 610-616 的 `subprocess.run` 替换为 `get_executor(user_id).exec_script(code, user_id=user_id, timeout=timeout, work_dir=work_dir)`。**新生成文件归档逻辑（620-636）依赖 work_dir 是宿主机可见目录** → 要求 `exec_script` 的挂载策略把 `files_dir(user_id)` 以**可写**方式挂入沙箱同一相对路径，沙箱退出后宿主机侧直接 `os.listdir(work_dir)` 即可归档（§4.1） |
| `cron_runner.py:190-197` `_execute_command_task` | `tools.execute_shell_command(content, timeout)` | 改为 `tools.execute_shell_command(content, timeout, user_id=task["user_id"])`（`task["user_id"]` 见 `cron_runner.py:82`）；黑名单校验保留 |

### 2.4 DockerExecutor 实现要点

- **调用方式**：`subprocess`/`asyncio` 调 `docker` CLI（`docker run --rm ... image sh -c <command>`），不引入 docker-py SDK（避免新依赖，CLI 在 Windows/Linux 通用）。
- **容器参数模板**（`exec_shell`）：

```
docker run --rm --interactive
  --name lobster-sb-{uid}-{ts8}
  --hostname lobster-sb-{uid}
  --workdir /work                       # 挂载点（§4.1）
  --mount type=bind,source={files_dir(uid)},target=/files,bind-propagation=rprivate
  --mount type=bind,source={data_dir},target=/data,ro
  --memory {SANDBOX_MEM_LIMIT} --memory-swap {SANDBOX_MEM_LIMIT}
  --cpus {SANDBOX_CPU_LIMIT} --pids-limit {SANDBOX_PIDS_LIMIT}
  --network {SANDBOX_NETWORK_MODE}      # none（默认）| sandbox-net
  --cap-drop ALL --security-opt no-new-privileges
  --user lobster                        # 非 root（镜像内 UID 10001）
  --stop-timeout 3 {SANDBOX_IMAGE} sh -c <command>
```

- **超时**：宿主侧 `timeout` 秒后 `docker kill {container}`（双保险：`sh -c` 内不包 `timeout`，避免与 shell 内联 `timeout` 命令歧义）；`exec_script` 额外在 `sh -c "python3 -B /tmp/_script_{uid}_{rand}.py"` 前把脚本经 stdin 写入容器临时路径（**规范选择：先 `docker cp` 脚本进容器再执行**，与现状"先落盘再执行"语义一致）。
- **user_id → 沙箱实例映射/复用策略**：
  - **默认不复用**（per-command `--rm` 容器）：隔离最彻底，无状态残留，开销 ~100-500ms 可接受（命令白名单多为低延迟操作，且 `exec_cmd` 本身有 30s 超时预算，`tools.py:104`）。
  - **可选长驻容器模式**（`SANDBOX_REUSE=long-lived`，非默认）：每 user 一个容器（`lobster-sb-{uid}`，首次 `docker create` 不启动，之后 `docker start` + `docker exec` 执行命令，空闲 `SANDBOX_IDLE_TIMEOUT`（默认 600s）后 `docker stop`）。复用可把单次开销降到 ~20ms，适合高频命令；代价是需管理容器生命周期、清理 `/tmp`、防止容器被脚本改坏后影响后续命令。**首期实现仅 per-command 模式，长驻模式作为后续优化项**（见 §6 T8，可延后）。
- **并发**：同一 user_id 的并发命令各自独立容器（容器名带时间戳+随机后缀防冲突）；不同 user 之间天然隔离。宿主侧对 `docker` CLI 调用加每用户信号量（默认 4）限制并发容器数，防止资源打满（§4.3）。

### 2.5 LocalExecutor（直通）

等价现状 `tools.py:73-79`：`subprocess.run(command, shell=True, capture_output=True, timeout=timeout, cwd=BASE_DIR)`。仅用于 admin（`SANDBOX_ADMIN_MODE=direct`）与 `user_id=0` 系统调用路径（§2.3）。

---

## 3. 配置项

统一前缀 `LOBSTER_SANDBOX_*`，从环境变量读取（与 `user_store.py:10-13` `MU_ADMIN_USERNAME` 等现有环境变量风格一致），模块级 `sandbox_config.py` 内解析，**进程启动时固化**（Docker 可用性探测已按 TTL 缓存，配置本身变更需重启，规范接受）。

| 配置项 | 默认值 | dev（本地 Windows） | prod（Linux/Docker） | 说明 |
|---|---|---|---|---|
| `LOBSTER_SANDBOX_ENABLED` | `true` | `true`（有 Docker Desktop 时） | `true` | 总开关。`false` 时所有角色走 LocalExecutor（等价现状，**仅允许在纯 dev 单机场景显式关闭**） |
| `LOBSTER_SANDBOX_MODE` | `docker` | `docker` | `docker` | 后端类型：`docker`（首期唯一实现）。预留 `firejail`/`disabled` 枚举，未实现的值启动时报错拒绝（防拼写错误静默直通） |
| `LOBSTER_SANDBOX_IMAGE` | `lobster-claw-sandbox:local` | 同左 | 同左 | 沙箱镜像名。`docker-compose.yml` 增加 sandbox 服务构建该镜像 |
| `LOBSTER_SANDBOX_FALLBACK` | `deny` | `deny` | `deny` | 沙箱后端不可用（Docker 未启动/镜像缺失）时的处置：`deny`=user 角色命令返回明确错误（默认）；`warn`=回退 LocalExecutor 执行并写审计日志+控制台告警（**仅限 dev**，prod 启动时检测到该值应拒绝启动或降级为 deny 并告警，见 §5.2） |
| `LOBSTER_SANDBOX_ADMIN_MODE` | `direct` | `direct` | `direct` | admin 角色行为：`direct`=直通（默认，保持现状）；`sandbox`=admin 也走沙箱 |
| `LOBSTER_SANDBOX_TIMEOUT` | `30` | 30 | 30 | 命令执行超时秒数（覆盖各调用方现有 30s 硬编码；`exec_cmd` 的 `tools.py:104`、`/exec` 的 `body.timeout` 仍优先取请求值，本项为默认上限） |
| `LOBSTER_SANDBOX_MEM_LIMIT` | `512m` | 512m | 1g | 容器 `--memory` |
| `LOBSTER_SANDBOX_CPU_LIMIT` | `1.0` | 1.0 | 2.0 | 容器 `--cpus` |
| `LOBSTER_SANDBOX_PIDS_LIMIT` | `128` | 128 | 256 | 容器 `--pids-limit`（防 fork 炸弹） |
| `LOBSTER_SANDBOX_NETWORK` | `none` | `none` | `none` | `none`=断网；`sandbox-net`=独立 bridge 网络（允许容器内 `ping`/`nslookup` 等网络诊断命令工作，但无法访问宿主内网） |
| `LOBSTER_SANDBOX_PER_USER_CONCURRENCY` | `4` | 4 | 8 | 每 user_id 并发容器数上限 |
| `LOBSTER_SANDBOX_IDLE_TIMEOUT` | `600` | 600 | 600 | （长驻模式用，首期忽略） |
| `LOBSTER_SANDBOX_HOST_CWD` | `BASE_DIR`（`lobster_mu/db.py`） | 同左 | 同左 | 容器内 `/work` 的宿主侧映射（脚本 work_dir、命令默认 cwd） |

**dev/prod 区分机制**：代码不自动探测环境，而是**部署侧显式注入**。`docker-compose.yml`（prod）统一设 `LOBSTER_SANDBOX_FALLBACK=deny`；本地开发用 `.env.dev`（新增，不入库）或 `web_server.py` 启动参数。启动自检（§5.2）把"prod + warn"组合判为配置错误。

---

## 4. 安全边界

### 4.1 挂载策略（per-user 目录）

| 宿主侧路径（来源） | 容器内路径 | 权限 | 用途 |
|---|---|---|---|
| `files_dir(user_id)` = `web/static/lobster-claw-files/{uid}/`（`paths.py:25-29`） | `/files` | **rw** | 脚本产物目录（`script_service.py:583` `work_dir`），脚本写文件后经宿主机归档（`script_service.py:620-636`）；命令产物也落此处 |
| `data/` = `BASE_DIR/data`（`paths.py:13` `USER_READ_ONLY_EXTRA`，现状对文件工具**只读**） | `/data` | **ro** | 与文件类工具读权限对齐（`paths.py:68-71`），供 `cat data/...` 等命令读取 |
| 命令默认 `cwd`（现状 `tools.py:78` `BASE_DIR`） | `/work` | 容器内 overlay（**不挂载宿主项目根**） | **关键变更**：现状 `execute_shell_command` 的 `cwd=BASE_DIR` 意味着 user 可在项目根下 `ls`/`cat` 到源码、`models.json` 等敏感文件。沙箱内 `/work` 为独立可写工作层（容器退出即销毁），如需访问项目文件必须经显式 ro 挂载（默认不挂） |
| `packages/`（`script_service.py:15` `PACKAGES_DIR`，全局共享 pip --target 目录） | `/packages` | **ro** | 脚本 `PYTHONPATH=/packages`（§8 P7 决议），保持现有第三方包 import 能力，只读防篡改 |
| `uploads_dir(user_id)`、`mu_files_dir(user_id)`（`paths.py:18-22,32-36`） | 默认**不挂载** | — | 现状 shell 命令本就无法越权访问（无路径映射），沙箱内维持不可见；如未来需要，加 ro 挂载并单列配置项 |

**写回策略**：
- 命令类（`exec_shell`）：沙箱内一切写操作只落在 `/work`（overlay，丢弃）与 `/files`（rw 挂载，保留）。规范**禁止** user 角色命令写 `/data`（ro 挂载，写会 `Read-only file system` 报错）。
- 脚本类（`exec_script`）：仅 `/files` 可写，且保留现有 `ALLOWED_FILE_EXTENSIONS`（`script_service.py:18-20`）归档白名单——沙箱内生成的其他扩展名文件在容器退出时随 `/work` overlay 丢弃，但 `/files` 挂载区的非白名单残留文件由宿主侧归档步骤清理（现状 `script_service.py:622-636` 只归档白名单、不删非白名单，规范**新增**：归档后删除 `/files` 中非白名单且不在 `before_files` 集合的残留文件）。
- 容器内禁止写入挂载点之外的任何宿主路径（无 ro/rw 挂载即不可见）。

### 4.2 网络

- 默认 `--network none`：`ping`/`nslookup`/`netstat`（白名单 `tools.py:31-32`）在断网容器内行为：`netstat` 仍可用（看 lo 接口），`ping`/`nslookup` 失败（无 DNS/无路由）。这是**有意的安全取舍**——user 不应有外联能力（现状 `curl`/`wget` 在黑名单 `tools.py:21`，但黑名单可绕过，沙箱断网是真正的兜底）。
- `LOBSTER_SANDBOX_NETWORK=sandbox-net`（可选）：独立 bridge，允许出站 TCP 但**不**暴露宿主端口；启用时需在文档中明示"user 命令可访问外网"的安全影响。

### 4.3 资源限制

| 限制 | 手段 | 默认 |
|---|---|---|
| CPU | `--cpus` | 1.0（dev）/ 2.0（prod） |
| 内存 | `--memory` + `--memory-swap`（swap 同值，禁 swap） | 512m / 1g |
| 进程数 | `--pids-limit` | 128 / 256 |
| 时间 | 宿主侧 `timeout` + `docker kill` | 30s（`exec_cmd` 上限），脚本 60s（`script_service.py:580` 默认） |
| 权限 | `--cap-drop ALL --security-opt no-new-privileges --user lobster`（非 root UID 10001） | 固定 |
| 磁盘 | 挂载区即宿主用户目录（受宿主卷容量限制）；`/work` overlay 限制 `--tmpfs /tmp:size=64m` | 64m tmpfs |
| 并发 | 每用户信号量（§2.4）+ 全局 Docker 调用并发上限（默认 16） | 4 / 16 |

### 4.4 审计

沙箱执行全部经过 `tools.log_operation`（`tools.py:40-57`），`operation` 字段规范为：
- `exec:sandbox`（user 走沙箱成功/失败）
- `exec:direct`（admin 直通 / `user_id=0` 系统调用，**detail 中记录 user_id=0 告警**）
- `sandbox:unavailable`（fallback 触发，success=False，error 记录原因：`docker-not-running` / `image-missing` / `fallback-deny`）
- `script:sandbox`（脚本沙箱执行）

---

## 5. 降级策略

### 5.1 沙箱不可用的判定

`DockerExecutor` 探测（`docker info`，TTL 30s 缓存）失败或 `docker run` 返回镜像缺失（`No such image`）时判定不可用。

### 5.2 处置矩阵（规范明确）

| 场景 | `SANDBOX_FALLBACK` | 行为 |
|---|---|---|
| user 角色 + Docker 不可用 | `deny`（**默认**） | 返回 `{"success": false, "error": "命令沙箱不可用（Docker 未就绪），user 角色禁止直接执行。请联系管理员。"}`；写 `sandbox:unavailable` 审计；**绝不**回退宿主机执行 |
| user 角色 + Docker 不可用 | `warn`（仅允许 dev） | 回退 LocalExecutor 执行；写 `sandbox:unavailable` 审计（success 按实际执行结果）；**服务启动时**检测到 `warn` 且环境疑似 prod（存在 `docker-compose` 运行标志或 `LOBSTER_ENV=prod`）→ 启动失败并提示改为 `deny` |
| admin 角色（`ADMIN_MODE=direct`）+ Docker 不可用 | 任意 | 不受影响，admin 本就走 LocalExecutor |
| `SANDBOX_ENABLED=false`（显式总开关关闭） | 任意 | 全角色直通（等价现状），启动日志输出**显著告警**："沙箱已禁用，所有用户命令将在宿主机直接执行"，写一次性审计 `sandbox:disabled` |
| 本地 Windows 无 Docker Desktop | — | 等同"Docker 不可用"，默认 `deny`。本地开发体验保障见 §8 P2（提供 `.env.dev` 模板 + 文档：开发 user 角色命令能力前必须先 `docker compose up lobster-sandbox` 或 `docker pull` 镜像） |

### 5.3 部分失败

`docker run` 中途失败（网络中断、磁盘满）：按 `SandboxResult.error` 返回命令级失败，不影响后续调用；连续 5 次失败触发探测缓存失效，重新 `docker info`。

---

## 6. 任务分解（按依赖顺序）

### T1. 沙箱镜像（无代码依赖，可最先并行）
- **新增** `sandbox/Dockerfile`：基于 `debian:bookworm-slim`（与 `Dockerfile:26` 运行时同系），安装 `coreutils procps iproute2 python3 python3-minimal`，创建非 root 用户 `lobster`（UID 10001），构建期断言 `ALLOWED_COMMANDS` 对应二进制存在（§1.3），`CMD ["sh"]`。
- **新增** `sandbox/README.md`：镜像用途、构建命令、与主镜像的关系。
- **修改** `docker-compose.yml`：新增 `lobster-sandbox` 服务（`build: ./sandbox`，仅构建不常驻，`container_name: lobster-sandbox-builder`，无 ports/volumes，`restart: "no"`，用于 `docker compose build` 产出镜像）；`mul-agent` 服务 `environment` 增加 `LOBSTER_SANDBOX_IMAGE`。

### T2. 配置层
- **新增** `lobster_mu/sandbox_config.py`：解析 §3 全部环境变量（`os.environ.get` + 默认值 + 枚举校验，非法值抛 `SandboxConfigError` 使启动失败），暴露 `config` 单例与 `reload()`。
- **修改** `web_server.py`：startup 阶段 import `sandbox_config` 做配置自检（prod+warn 拒绝、`ENABLED=false` 显著告警）。

### T3. 执行器抽象与 Docker 后端
- **新增** `lobster_mu/sandbox.py`：`SandboxResult`、`SandboxExecutor`（ABC）、`LocalExecutor`（移植 `tools.py:73-89` 逻辑）、`DockerExecutor`（§2.4 全部要点：CLI 调用、容器参数模板、超时 kill、探测缓存、每用户信号量、审计钩子）、`get_executor(user_id)` 角色判定入口。
- 依赖：T1（镜像）、T2（配置）。

### T4. 嵌入 tools.py（exec 主路径）
- **修改** `lobster_mu/tools.py`：
  - `exec_cmd(command, user_id=0)`（92-117）：签名加 `user_id`，内部 `execute_shell_command(command, timeout=30, user_id=user_id)`。
  - `execute_shell_command(command, timeout=30, user_id=0)`（70-89）：签名加 `user_id`，内部改调 `sandbox.get_executor(user_id).exec_shell(...)`，`SandboxResult → dict` 转换保持**返回结构不变**（`success/stdout/stderr/return_code/error`，兼容 `cron_runner.py:198-204` 的读取）。
  - `execute_tool_call`（490-491）：`exec_cmd(tool_call.get("command",""), user_id)`。
- 依赖：T3。

### T5. 嵌入 HTTP /exec 端点
- **修改** `web/routes/lobster_mu.py`：
  - `mu_exec`（677-685）：改为 `run_in_executor` 调用 `tools.exec_cmd(body.command, user["id"])`（补齐白名单缺口），返回结构适配现有 `{"success","stdout","stderr","return_code"}`（exec_cmd 返回 markdown 字符串，需在路由层从 `SandboxResult` 取结构化数据——**实现方式**：路由层改调 `tools.execute_shell_command` 之前先调 `tools.exec_cmd` 做校验、再调 `sandbox.get_executor(user["id"]).exec_shell` 取结构化结果；或 exec_cmd 增加 `raw=True` 返回 `SandboxResult`）。
  - 删除 `_async_shell`（688-706）。
- 依赖：T3、T4。

### T6. 嵌入 script_service
- **修改** `lobster_mu/script_service.py`：
  - `execute_python_script`（580-616）：`subprocess.run(['python','-B',script_path])` 替换为 `sandbox.get_executor(user_id).exec_script(code, user_id=user_id, timeout=timeout, work_dir=work_dir)`；`exec_script` 内部把 `code` 写入 `work_dir` 下临时脚本（等价现状 587-588 落盘）再经沙箱执行。
  - 新增归档后残留清理（§4.1 写回策略：删除 `/files` 中非白名单且非 `before_files` 的文件）。
  - `DockerExecutor.exec_script` 的挂载必须包含 `work_dir`（即 `files_dir(user_id)`，§4.1 已覆盖）与 `packages/`（ro）。
- 依赖：T3。

### T7. 嵌入 cron_runner
- **修改** `lobster_mu/cron_runner.py`：`_execute_command_task`（195-196）`tools.execute_shell_command(content, timeout)` → `tools.execute_shell_command(content, timeout, user_id=task["user_id"])`（`task["user_id"]` 取自 `cron_runner.py:82` 透传）。
- 依赖：T4。

### T8.（可延后）长驻容器复用模式
- **修改** `lobster_mu/sandbox.py`：`SANDBOX_REUSE=long-lived` 分支（§2.4），容器生命周期管理（create/start/exec/stop-on-idle）+ 定期 GC 协程挂到 `web_server.py` startup/shutdown。
- 依赖：T3。

### T9. 验收测试
- **新增** `tests/test_sandbox_spec.py`（或项目现有测试目录）：覆盖 §7 全部验收点（Docker 可用时真跑，不可用时 mock `docker info` 失败路径测 fallback）。
- 依赖：T4-T7。

**实施顺序**：T1 ∥ T2 → T3 → T4 → {T5 ∥ T6 ∥ T7} → T9（T8 独立延后）。

---

## 7. 验收标准（可测试）

前置：`docker compose build` 已产出 `lobster-sandbox:local` 镜像；测试用户 `user_test`（role=user）与 `admin`（bootstrap 管理员，`user_store.py:32-47`）已创建。

| # | 验收点 | 验证方法 |
|---|---|---|
| A1 | user 角色 `whoami` 返回沙箱内用户而非宿主机用户 | user 登录调 `/api/lobster-mu/exec` `{command:"whoami"}` → `stdout` 含 `lobster`（容器 UID 10001 用户名），**不含**宿主机用户（Windows: `admin`/Linux: 部署用户） |
| A2 | user 角色 `cat /etc/passwd` 受限于沙箱视图 | 同上 `{command:"cat /etc/passwd"}` → 内容仅含沙箱镜像的 debian 默认用户 + `lobster`，**不含**宿主机 `/etc/passwd` 条目 |
| A3 | user 角色 `hostname` 为沙箱主机名 | `{command:"hostname"}` → `lobster-sb-{uid}` |
| A4 | user 角色无法读宿主项目源码 | `{command:"ls /work"}` → 仅 `/work` 空工作层内容；`{command:"cat /data/models.json"}`（data ro 挂载存在时）可读，但 `{command:"cat /app/models.json"}` → `No such file or directory`（主镜像路径不可见） |
| A5 | user 角色脚本产物写回用户目录 | `/api/lobster-mu/script/execute` 提交写相对路径文件的代码 → `generated_files` 含归档条目，宿主 `files_dir(uid)` 下可见（验证 §4.1 rw 挂载） |
| A6 | user 角色断网（默认） | `{command:"ping -c1 8.8.8.8"}` → 失败（无网络）；`netstat` 仍返回 lo 接口 |
| A7 | 资源限制生效 | 脚本 `while True: pass` 提交 `timeout:5` → 5s 后返回 `success:false, error:"命令执行超时"`，且容器已被 kill（`docker ps -a` 无残留 `lobster-sb-*`） |
| A8 | 白名单缺口修复：HTTP /exec 拒绝非白名单命令 | user 调 `/exec` `{command:"env"}`（env 不在 `ALLOWED_COMMANDS`）→ 被拒，error 含"不在允许列表"（现状 `lobster_mu.py:680` 只查黑名单） |
| A9 | admin 行为不变（`ADMIN_MODE=direct`） | admin 调 `/exec` `{command:"whoami"}` → 返回宿主机用户；admin `cat /app/models.json`（主容器内路径）→ 可读（直通无挂载限制） |
| A10 | 沙箱不可用返回明确错误（fallback=deny） | `docker stop` Docker Desktop → user 调 `/exec` → `success:false`，error 含"命令沙箱不可用"，**且宿主机上未执行任何命令**（审计日志出现 `sandbox:unavailable`，无 `exec:sandbox` 成功记录） |
| A11 | user_id=0 系统路径直通并告警 | cron 任务以 system 身份（无 user 上下文）触发 → 走 LocalExecutor，审计 `exec:direct` 且 detail 含 `user_id=0` 标记（见 §8 P5 决议） |
| A12 | 审计完整性 | A1-A10 每次执行后 `mu_operation_logs` 出现对应记录（`tools.py:48-52`），operation 值符合 §4.4 规范 |
| A13 | 并发限制 | 同一 user 并发 10 个 `/exec` → 前 4 个执行，后 6 个排队（信号量）或返回"并发超限"错误（§2.4），Docker 侧 `docker ps` 同 uid 容器数 ≤4 |

---

## 8. 风险与开放问题（需用户决策）

### P1. admin 是否也沙箱化？（配置 `LOBSTER_SANDBOX_ADMIN_MODE`）—— **已决议：direct**
- **决议（用户确认）**：admin 保留 `direct`（直通），与现状兼容。仅 user 角色沙箱化。
- **实现影响**：`LOBSTER_SANDBOX_ADMIN_MODE` 默认 `direct`，`sandbox` 值保留为可选配置项（供未来安全加固启用）。A9 验收点保持"admin 行为不变"。
- 风险（接受）：admin 账号被盗用时无隔离兜底，由运维侧密钥管理与审计承担。

### P2. 本地 Windows 开发是否强制 Docker？—— **已决议：deny**
- **决议（用户确认）**：本地 dev 默认 `deny`，与 prod 行为一致。Windows 开发机无 Docker Desktop 时 user 角色命令/脚本直接拒绝并返回明确错误（admin 可执行）。
- **实现影响**：开发文档 + `.env.dev` 模板不设 `FALLBACK=warn`，而是提示"开发 user 命令能力前必须先 `docker compose build lobster-sandbox` 或安装 Docker Desktop（WSL2 后端）"。`warn` 模式保留为可选配置项，但默认不启用。

### P3. 主容器内运行沙箱容器的嵌套问题（prod Docker 部署）—— **已决议：(c)**
- **决议（用户确认）**：prod 形态选 **(c)：`python web_server.py` 直跑 Linux 主机 + Docker 沙箱**。mul-agent 在 prod 不以容器形式部署，直接运行在宿主机，调用宿主 Docker 启动沙箱容器，无 docker.sock 挂载、无嵌套问题。
- `docker-compose.yml` 的容器化形态仅保留给 **dev/staging**，若 dev 用容器跑 mul-agent 并接受 docker.sock 挂载，按 P4 缓解措施处理（非默认）。
- **实现影响**：prod 部署文档需说明"mul-agent 直跑宿主机 + 安装 Docker Engine"，`deploy.sh` 增加 prod 直跑分支（不 `docker compose up mul-agent`，而是 `python web_server.py` + `docker compose build lobster-sandbox`）。

### P4. docker.sock 挂载的攻击面（仅 dev/staging 容器形态适用）
- 已降级为 dev/staging 可选路径。缓解措施（若启用）：sock 只读挂载 + 主容器 drop 全部 capabilities + seccomp 限制 `connect` 到 unix sock 的 syscalls。prod 不触及此问题。

### P5. `user_id=0` / 系统调用路径的语义
- 现状 `execute_shell_command` 多处被无 user 上下文调用（cron 的 system 任务、内部工具）。规范 §2.3 暂按"直通+审计告警"处理。
- **决策点**：是否引入 `system` 伪角色（`users` 表外）显式承载系统任务，避免 `user_id=0` 歧义？

### P6. 命令白名单是否保留？
- 沙箱是第二层防御，但 §1.3 指出白名单在沙箱内有"命令不存在"的兼容性问题（Windows 系命令）。
- **决策点**：(a) 保留白名单（纵深防御，沙箱内不可用命令返回 not found）——**规范推荐**；(b) 沙箱内放宽白名单（既然已隔离，允许任意命令）——风险是沙箱逃逸时的爆炸半径扩大，不推荐；(c) 分角色：user 白名单+沙箱，admin 无白名单直通（现状）。

### P7. 脚本沙箱的 PYTHONPATH 依赖
- 现状 `execute_python_script` 把 `packages/`（`script_service.py:15`，全局共享 pip --target 目录）注入子进程 `PYTHONPATH`（600-604）。沙箱化后 `packages/` 目录**未挂载**（§4.1），脚本将无法 import 已安装的第三方包（numpy/pandas 等），**破坏现有脚本能力**。
- **决策点**：(a) 沙箱镜像内 `--mount type=bind,source={packages_dir},target=/packages,ro` + 容器内 `PYTHONPATH=/packages`（推荐，与现状语义对齐，packages 只读防篡改）；(b) 脚本沙箱独立 `pip install` 到容器内 `/tmp`（每次开销大）；(c) 脚本不沙箱化仅命令沙箱化（**不推荐**，Python 脚本是最强逃逸通道，§0.1）。
- **规范已采纳 (a)**，见 §4.1 挂载表与 T6。

### P8. 超时 kill 的可靠性
- `docker kill` 后容器内进程组（`sh -c` 派生的子进程）是否全部终止？`--stop-timeout 3` + `sh` 不转发信号给子进程的风险。
- **缓解**（已纳入 T3 实现要求，非开放问题但需验证）：容器内用 `sh -c "trap 'kill 0' TERM; <command>"` 或 `setsid` + kill 进程组。A7 验收点覆盖。

### P9. 镜像信任
- 沙箱镜像若被篡改（registry 投毒）则隔离失效。**缓解**：`docker-compose.yml` 本地 build（不经 registry），prod 用镜像 digest 固定。

---

## 附录：关键代码位置索引

| 符号 | 位置 |
|---|---|
| `execute_shell_command` | `lobster_mu/tools.py:70-89` |
| `exec_cmd` | `lobster_mu/tools.py:92-117` |
| `DANGEROUS_COMMANDS` / `ALLOWED_COMMANDS` | `lobster_mu/tools.py:15-35` |
| `execute_tool_call`（exec 分支 490-491） | `lobster_mu/tools.py:484-525` |
| `log_operation` | `lobster_mu/tools.py:40-57` |
| `mu_exec` / `_async_shell` | `web/routes/lobster_mu.py:677-706` |
| `mu_script_execute` | `web/routes/lobster_mu.py:605-618` |
| `check_user_rate`（user 限流，admin 无此依赖） | `web/routes/lobster_mu.py:350-358` |
| `execute_python_script` | `lobster_mu/script_service.py:580-659` |
| `PACKAGES_DIR` / `ALLOWED_FILE_EXTENSIONS` | `lobster_mu/script_service.py:15,18-20` |
| `_execute_command_task` | `lobster_mu/cron_runner.py:187-207`（`task["user_id"]` 见 82 行） |
| `require_admin` / `get_mu_user` | `lobster_mu/security.py:28-42` |
| `users.role` / `get_by_id` / bootstrap admin | `lobster_mu/user_store.py:24,58-64,32-47` |
| `resolve_user_path` / `files_dir` / `USER_READ_ONLY_EXTRA` | `lobster_mu/paths.py:85-94,25-29,13` |
| 主镜像定义 / compose 卷挂载 | `Dockerfile:26-69`、`docker-compose.yml:1-30` |

---

**文档说明**：本规范覆盖方案选型、架构、配置、安全边界、降级、任务分解、验收、风险八部分。

### 决议汇总（用户已确认）

| 问题 | 决议 | 影响 |
|---|---|---|
| P1 admin 沙箱化 | **direct**（admin 直通，仅 user 沙箱） | A9 保持，`ADMIN_MODE` 默认 `direct` |
| P2 本地 dev 降级 | **deny**（与 prod 一致） | `.env.dev` 不设 warn，需先 build 沙箱镜像 |
| P3 prod 部署形态 | **(c) 宿主机直跑 + Docker 沙箱** | prod 不容器化 mul-agent，`deploy.sh` 增加直跑分支 |
| P7 脚本 PYTHONPATH | **(a) packages/ ro 挂载 + PYTHONPATH=/packages** | 已纳入 §4.1 挂载表与 T6 |

其余 P4（docker.sock，仅 dev/staging 可选）、P5（user_id=0 直通+告警）、P6（保留白名单，推荐 a）、P8（kill 可靠性，T3 实现要求）、P9（镜像本地 build + digest 固定）按推荐值采纳，非阻塞。
