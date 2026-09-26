# 龙虾Claw 用户命令沙箱镜像
# 基础镜像：dify-agent-local-sandbox（Debian bookworm + Python 3.12）
# 说明：iproute2/tree/iputils-ping 因 apt 网络不通未安装，对应白名单项(ip/netstat/tree/ping)在容器内不可用
#
# 中国网络无法直连 Docker Hub，构建时请用国内镜像源覆盖 BASE_IMAGE，例如：
#   docker compose build --build-arg BASE_IMAGE=docker.xuanyuan.me/langgenius/dify-agent-local-sandbox:1.16.1 lobster-sandbox
# 可用源（2026 实测）：docker.xuanyuan.me / docker.1ms.run / docker.m.daocloud.io / docker.aityp.com
ARG BASE_IMAGE=langgenius/dify-agent-local-sandbox:1.16.1
FROM ${BASE_IMAGE}

# python 软链已存在（/usr/local/bin/python），无需处理

# dify sandbox 基础镜像以 dify 用户运行，重置为 root 以执行系统级操作
ENTRYPOINT []
USER root

# 非 root 用户（UID 10001，避免与宿主常见 UID 冲突）
RUN groupadd -g 10001 lobster 2>/dev/null || true; \
    useradd -u 10001 -g lobster -m -s /bin/sh lobster 2>/dev/null || true

# 构建期断言：基础命令（dify sandbox 已含）对应二进制必须存在，缺失则构建失败
# 不含 ip/netstat/tree/ping（apt 网络不通未装）
RUN for c in echo ls cat find grep date whoami hostname uname ps pwd head tail wc cut split join sort; do \
      command -v "$c" >/dev/null 2>&1 || { echo "ERROR: missing command: $c" >&2; exit 1; }; \
    done

# 沙箱工作目录（/work overlay 由运行时 --workdir 指定，此处仅预创建）
RUN mkdir -p /work /files /data /packages && \
    chown -R lobster:lobster /work /files /packages

WORKDIR /work

# 默认 shell（运行时以 sh -c <command> 覆盖）
CMD ["sh"]
