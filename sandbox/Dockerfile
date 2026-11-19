# 龙虾Claw 用户命令沙箱镜像
# 基础镜像：官方 python:3.11-slim-bookworm（Debian bookworm）
#
# 为什么不用 langgenius/dify-agent-local-sandbox：
#   1) 国内镜像源经常缺缓存/返回 503，构建不稳定
#   2) 它是 Python 3.12，而主容器（mul-agent）是 Python 3.11，packages/ 下由主容器
#      pip --target 装出的 cp311 wheel 在 3.12 里无法 import（numpy/scipy 等 C 扩展
#      直接失败）。改用 3.11 后主容器与沙箱 ABI 完全一致。
#   3) 官方镜像无自定义用户/entrypoint，体积也更小
#
# 中国网络无法直连 Docker Hub 时用镜像源覆盖 BASE_IMAGE（注意官方镜像带 library/ 前缀）：
#   docker compose build \
#     --build-arg BASE_IMAGE=docker.xuanyuan.me/library/python:3.11-slim-bookworm \
#     lobster-sandbox
# 可用源（2026 实测）：docker.xuanyuan.me / docker.m.daocloud.io / docker.1ms.run / docker.aityp.com
ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

# 以 root 执行系统级安装，运行时由 docker run --user lobster 降权
# ENTRYPOINT 置空：BASE_IMAGE 可被覆盖，避免基础镜像自带 entrypoint 干扰 sh -c 执行
ENTRYPOINT []
USER root

# 非 root 用户（UID 10001，避免与宿主常见 UID 冲突）
RUN groupadd -g 10001 lobster 2>/dev/null || true; \
    useradd -u 10001 -g lobster -m -s /bin/sh lobster 2>/dev/null || true

# 系统工具 + 中文字体（一次安装，减少层数）
#   iproute2(ip) / iputils-ping(ping) / procps(ps) / tree / hostname 供脚本白名单命令使用
#   字体装不上直接构建失败，避免静默产出“中文全变方块”的镜像
RUN set -eux; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list 2>/dev/null || true; \
    fi; \
    if ls /etc/apt/sources.list.d/*.sources >/dev/null 2>&1; then \
      sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl iproute2 iputils-ping net-tools procps tree hostname \
        fonts-wqy-zenhei fonts-wqy-microhei fonts-droid-fallback fontconfig; \
    fc-cache -fv; \
    test -n "$(fc-list :lang=zh -f '%{file}\n')" || { \
      echo "ERROR: 未安装到任何中文字体（fonts-wqy-zenhei 等），请检查 apt 源/网络后重新构建" >&2; \
      exit 1; \
    }; \
    rm -rf /var/lib/apt/lists/*

# 预装常用科学计算包的“老 CPU 兼容版”：
# numpy 2.3+ / scipy 1.14+ 的 wheel 要求 CPU 支持 X86_V2 指令集，老服务器 CPU
# 不支持会 import 崩溃（RuntimeError: baseline optimizations X86_V2）。
# 这里锁到不要求 V2 的版本，且作为系统包安装——用户脚本 import 时系统包优先，
# 无需用户自行安装，也避免用户装到不兼容版本。
# 版本兼容矩阵：numpy 2.2.6 + pandas 2.2.3 + scipy 1.13.1 + matplotlib 3.8.4
# （matplotlib 3.9+ 需 numpy>=2.0，3.8.x 同时兼容 numpy 2.2 且不强制 V2）
RUN python3 -m pip install --no-cache-dir \
        "numpy==2.2.6" "pandas==2.2.3" "scipy==1.13.1" "matplotlib==3.8.4" \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
    || python3 -m pip install --no-cache-dir "numpy==2.2.6" \
        -i https://pypi.tuna.tsinghua.edu.cn/simple

# 构建期断言：预装的包必须能在当前镜像/CPU 正常 import（防装到不兼容版本）
RUN python3 -c "import numpy, pandas, scipy, matplotlib; print('preinstalled ok', numpy.__version__, pandas.__version__, scipy.__version__, matplotlib.__version__)"

# 预装 fpdf2（PDF 生成）+ fonttools（TTC 字体集转单字体）；缺库会让用户 PDF 脚本直接失败
RUN python3 -m pip install --no-cache-dir \
        "fpdf2>=2.7" "fonttools" \
        -i https://pypi.tuna.tsinghua.edu.cn/simple

# 配置 matplotlib 默认使用中文字体（对所有用户脚本生效）：
# 把 matplotlibrc 放到固定目录并通过 MPLCONFIGDIR 指向它。
RUN mkdir -p /opt/mplconfig && \
    python3 - <<'PY'
import os
cfg = os.path.join('/opt/mplconfig', 'matplotlibrc')
with open(cfg, 'w', encoding='utf-8') as f:
    f.write("font.sans-serif: WenQuanYi Zen Hei, DejaVu Sans\n")
    f.write("axes.unicode_minus: False\n")
print('matplotlibrc written:', cfg)
PY
ENV MPLCONFIGDIR=/opt/mplconfig
# 预热 matplotlib 字体缓存（构建期生成 fontlist，运行时无需重新扫描）
RUN python3 -c "import matplotlib.font_manager as fm; _ = fm.findfont('WenQuanYi Zen Hei'); print('font ok:', _)"
# 运行时沙箱以 lobster 用户执行，确保其对配置/缓存目录可读写（放在预热之后，
# 否则根用户生成的 fontlist 会属于 root，lobster 无法重建缓存）
RUN chown -R lobster:lobster /opt/mplconfig

# 构建期断言：fpdf2 能加载系统中文字体并成功输出含中文的 PDF（失败即构建失败，
# 避免运行期出现“无法加载中文字体”）
RUN python3 - <<'PY'
import subprocess
from fpdf import FPDF
font = subprocess.check_output(["fc-list", ":lang=zh", "-f", "%{file}\n"]).decode().strip().splitlines()[0]
assert font, "no CJK font found"
if font.lower().endswith((".ttc", ".otc")):
    from fontTools.ttLib import TTCollection
    ttf = "/tmp/cjk_font.ttf"
    TTCollection(font, lazy=True).fonts[0].save(ttf)
    font = ttf
pdf = FPDF()
pdf.add_page()
pdf.add_font("CJK", "", font)
pdf.set_font("CJK", "", 12)
pdf.cell(0, 10, "中文字体测试", new_x="LMARGIN", new_y="NEXT")
pdf.output("/tmp/font_test.pdf")
print("pdf font ok:", font)
PY

# 内置字体挂载点（运行时把宿主机 assets/fonts bind 到这里，只读）
RUN mkdir -p /opt/lobster/fonts && chown -R lobster:lobster /opt/lobster

# 构建期断言：白名单命令对应二进制必须存在，缺失则构建失败
# （netstat 来自 net-tools，旧 dify 基础镜像缺它导致白名单项不可用，现已补齐）
RUN for c in echo ls cat find grep date whoami hostname uname ps pwd head tail wc cut split join sort ip ping netstat tree; do \
      command -v "$c" >/dev/null 2>&1 || { echo "ERROR: missing command: $c" >&2; exit 1; }; \
    done

# 沙箱工作目录（/work overlay 由运行时 --workdir 指定，此处仅预创建）
RUN mkdir -p /work /files /data /packages && \
    chown -R lobster:lobster /work /files /packages

WORKDIR /work

# 默认 shell（运行时以 sh -c <command> 覆盖）
CMD ["sh"]
