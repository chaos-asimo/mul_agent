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

# 预装常用科学计算包的“老 CPU 兼容版”：
# numpy 2.3+ / scipy 1.14+ 的 wheel 要求 CPU 支持 X86_V2 指令集，老服务器 CPU
# 不支持会 import 崩溃（RuntimeError: baseline optimizations X86_V2）。
# 这里锁到不要求 V2 的版本，且作为系统包安装——用户脚本 import 时系统包优先，
# 无需用户自行安装，也避免用户装到不兼容版本。
# 版本兼容矩阵：numpy 2.2.6 + pandas 2.2.3 + scipy 1.13.1 + matplotlib 3.8.4
# （matplotlib 3.9+ 需 numpy>=2.0，3.8.x 同时兼容 numpy 2.2 且不强制 V2）
RUN python3 -m pip install --no-cache-dir --break-system-packages \
        "numpy==2.2.6" "pandas==2.2.3" "scipy==1.13.1" "matplotlib==3.8.4" \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
    || python3 -m pip install --no-cache-dir "numpy==2.2.6" \
        -i https://pypi.tuna.tsinghua.edu.cn/simple

# 构建期断言：预装的包必须能在当前镜像/CPU 正常 import（防装到不兼容版本）
RUN python3 -c "import numpy, pandas, scipy, matplotlib; print('preinstalled ok', numpy.__version__, pandas.__version__, scipy.__version__, matplotlib.__version__)"

# 预装中文字体（文泉驿正黑），让 matplotlib 中文标题/坐标轴不乱码、不出方块。
# 1) 换国内 apt 源并安装字体 + fontconfig；apt 失败不阻断构建（仅退化为无中文字体）
RUN set -eux; \
    if [ -f /etc/apt/sources.list ] || ls /etc/apt/sources.list.d/*.sources >/dev/null 2>&1; then \
      sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    fi; \
    apt-get update \
      && apt-get install -y --no-install-recommends fonts-wqy-zenhei fontconfig \
      && fc-cache -fv \
      || echo "WARN: apt 安装中文字体失败，中文显示可能受影响（不影响构建）"

# 2) 配置 matplotlib 默认使用中文字体（对所有用户脚本生效）：
#    把 matplotlibrc 放到固定目录并通过 MPLCONFIGDIR 指向它。
RUN mkdir -p /opt/mplconfig && \
    python3 - <<'PY'
import matplotlib, os
cfg = os.path.join('/opt/mplconfig', 'matplotlibrc')
with open(cfg, 'w', encoding='utf-8') as f:
    f.write("font.sans-serif: WenQuanYi Zen Hei, DejaVu Sans\n")
    f.write("axes.unicode_minus: False\n")
print('matplotlibrc written:', cfg)
PY
ENV MPLCONFIGDIR=/opt/mplconfig
# 运行时沙箱以 lobster 用户执行，确保其对配置/缓存目录可读写
RUN chown -R lobster:lobster /opt/mplconfig
# 预热 matplotlib 字体缓存（构建期生成 fontlist，运行时无需重新扫描）
RUN python3 -c "import matplotlib.font_manager as fm; _ = fm.findfont('WenQuanYi Zen Hei'); print('font ok:', _)"

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
