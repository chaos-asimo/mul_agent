# 龙虾Claw 用户命令沙箱镜像

## 用途

为 v3 龙虾Claw 的 **user 角色** 命令与 Python 脚本执行提供 Docker 容器级隔离，
使其不在宿主机（或主容器）直接执行，防止 shell 注入 / 脚本 `subprocess` 逃逸。

- admin 角色：直通执行（`LOBSTER_SANDBOX_ADMIN_MODE=direct`，默认），不使用本镜像。
- user 角色：每条命令以 `docker run --rm` 启动一个本镜像的临时容器执行，容器退出即销毁。

## 构建

```bash
# 在项目根目录
docker compose build lobster-sandbox
# 或
docker build -t lobster-claw-sandbox:local ./sandbox
```

构建期会自动断言白名单命令（Linux 子集）的二进制存在，缺失则构建失败。

## 与主镜像的关系

| 项 | 说明 |
|---|---|
| 基础镜像 | `debian:bookworm-slim`，与运行时 `python:3.11-slim-bookworm` 同系 |
| 构建位置 | 本地 `docker compose build`，不经 registry（§8 P9 防镜像投毒） |
| 是否常驻 | 否。`lobster-sandbox` 服务仅用于构建产出镜像，`restart: "no"` |
| 调用方式 | 由 `lobster_mu/sandbox.py` 的 `DockerExecutor` 通过 `docker` CLI 调用 |

## 容器运行参数（DockerExecutor 注入）

- `--user lobster`（非 root，UID 10001）
- `--network none`（默认断网，`LOBSTER_SANDBOX_NETWORK` 可改 `sandbox-net`）
- `--cap-drop ALL --security-opt no-new-privileges`
- `--memory / --cpus / --pids-limit`（资源限制）
- 挂载：`/files`(rw 用户产物)、`/data`(ro)、`/packages`(ro)、`/work`(overlay 不挂宿主项目根)

详见 `spec/user-command-sandbox/spec.md` §2.4、§4。
