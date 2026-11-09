# -*- coding: utf-8 -*-
"""中文字体定位（全项目共用，避免各处硬编码同一份路径清单）。

查找优先级：
1. 环境变量 LOBSTER_CJK_FONT（字体文件或其所在目录）
2. fc-list 动态查询（Linux + fontconfig）
3. matplotlib font_manager 已注册字体（按常见中文字体名匹配）
4. 常见目录 glob（Noto CJK / 思源 / 文泉驿等）
5. 历史沿用的绝对路径兜底（Windows / macOS / 常见 Linux 发行版）

返回字体文件绝对路径；找不到返回 None，由调用方决定是否回退（如 Arial）。
结果会缓存，避免每次生成 PDF 都重新扫描。
"""
import functools
import glob
import os
import re
import subprocess

ENV_VAR = 'LOBSTER_CJK_FONT'

_FONT_EXTS = ('.ttf', '.ttc', '.otf', '.otc')

# 命中越靠前越优先
_PREFERRED = (
    'wqy-zenhei', 'wqy-microhei', 'wenquanyi',
    'notosanscjk', 'sourcehansans', 'notoserifcjk', 'sourcehanserif',
    'microsoftyahei', 'msyh', 'pingfangsc', 'pingfang',
    'heiti', 'simhei', 'simsun', 'arialuni', 'droidsansfallback',
    'songti', 'fangsong',
)

_GLOB_PATTERNS = (
    '/usr/share/fonts/**/NotoSansCJK*',
    '/usr/share/fonts/**/NotoSerifCJK*',
    '/usr/share/fonts/**/SourceHanSans*',
    '/usr/share/fonts/**/SourceHanSerif*',
    '/usr/share/fonts/**/wqy-*.tt*',
    '/usr/local/share/fonts/**/*CJK*',
    '/usr/local/share/fonts/**/*Han*',
    '/Library/Fonts/*CJK*',
    '/System/Library/Fonts/*CJK*',
    'C:/Windows/Fonts/msyh*',
    'C:/Windows/Fonts/simsun*',
    'C:/Windows/Fonts/simhei*',
)

_FALLBACK_PATHS = (
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/simsun.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/kaiu.ttf',
    'C:/Windows/Fonts/arialuni.ttf',
    '/Library/Fonts/Noto Sans CJK SC.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
)

# 内置字体目录（随仓库分发，不依赖宿主机/镜像是否装了字体）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED_FONT_DIRS = (
    os.path.join(_PROJECT_ROOT, 'assets', 'fonts'),
    '/opt/lobster/fonts',
)

_cache = {'checked': False, 'path': None}


def _is_font_file(path):
    try:
        return bool(path) and path.lower().endswith(_FONT_EXTS) and os.path.isfile(path)
    except (OSError, TypeError):
        return False


def _is_extension_font(path):
    """排除只有生僻字扩展区的字体（如 SimSun-ExtG），它们没有常用汉字。"""
    name = os.path.basename(path).lower()
    return any(tag in name for tag in ('extg', 'extb', 'extc', 'extd', 'extf'))


_CJK_PROBE_CHARS = (0x4E2D, 0x3002, 0x4E00)          # 中 。 一


@functools.lru_cache(maxsize=64)
def covers_common_cjk(path):
    """字体是否真的含常用汉字字形；无法判定时按“可用”处理（返回 True）。

    fc-list / glob 可能先命中纯西文或符号字体，拿它注册 fpdf/matplotlib 会让
    所有中文都缺字形 → PDF 页面看起来是空白却不报错。这里直接排除这类字体。
    """
    try:
        from fontTools.ttLib import TTFont, TTCollection
        if path.lower().endswith(('.ttc', '.otc')):
            coll = TTCollection(path, lazy=True)
            font = coll.fonts[0] if coll.fonts else None
        else:
            font = TTFont(path, lazy=True, fontNumber=0)
        if font is None:
            return True
        try:
            cmap = font.getBestCmap() or {}
            return any(cp in cmap for cp in _CJK_PROBE_CHARS)
        finally:
            font.close()
    except Exception:
        return True


def _score(path):
    """字体优先级打分：越小的越优先（常规体优于粗体/斜体/细体）。"""
    low = os.path.basename(path).lower().replace(' ', '').replace('_', '')
    rank = len(_PREFERRED)
    for i, key in enumerate(_PREFERRED):
        if key in low:
            rank = i
            break
    if re.search(r'(bd|bold|black|heavy|italic|oblique)(\.|$)', low):
        rank += len(_PREFERRED)          # Windows 粗体后缀（msyhbd.ttc）
    if re.search(r'(light|thin|l)\.(tt[cf]|ot[cf])$', low):
        rank += len(_PREFERRED)          # Windows 细体后缀（msyhl.ttc）
    return rank


def _best(candidates):
    fonts = [
        p for p in candidates
        if _is_font_file(p) and not _is_extension_font(p)
    ]
    if not fonts:
        return None
    # 排序键保证结果稳定：优先级 > 是否常规体 > 文件名短 > 字典序
    fonts = sorted(
        set(fonts),
        key=lambda p: (_score(p), len(os.path.basename(p)), os.path.basename(p).lower()),
    )
    # 优先选真正含汉字的字体；全都不含时退回原行为，避免“无字体可用”
    covered = [p for p in fonts if covers_common_cjk(p)]
    return (covered or fonts)[0]


def _from_env():
    val = (os.environ.get(ENV_VAR) or '').strip().strip('"')
    if not val:
        return None
    if _is_font_file(val):
        return val
    if os.path.isdir(val):
        return _best(glob.glob(os.path.join(val, '*')))
    return None


def _from_bundled():
    """内置字体目录（随仓库分发，优先级仅次于显式环境变量）。"""
    candidates = []
    for d in BUNDLED_FONT_DIRS:
        try:
            candidates.extend(glob.glob(os.path.join(d, '*')))
        except (OSError, ValueError):
            continue
    return _best(candidates)


def bundled_font_dir():
    """返回存在的内置字体目录（供沙箱挂载/环境变量注入用）；没有则 None。"""
    for d in BUNDLED_FONT_DIRS:
        try:
            if os.path.isdir(d) and _best(glob.glob(os.path.join(d, '*'))) is not None:
                return d
        except (OSError, ValueError):
            continue
    return None


def ensure_ttf_path(path):
    """把 .ttc 字体集转成单字体 .ttf（旧版 PyFPDF 不支持 TTC 时兜底）。
    非 TTC、转换失败或 fontTools 缺失时原样返回，不改变原行为。"""
    try:
        p = str(path or '')
        if not p.lower().endswith('.ttc') or not os.path.isfile(p):
            return path
        import tempfile
        from fontTools.ttLib import TTCollection
        cache_dir = os.path.join(tempfile.gettempdir(), 'lobster_fonts')
        os.makedirs(cache_dir, exist_ok=True)
        out = os.path.join(cache_dir, os.path.basename(p)[:-4] + '.0.ttf')
        if not os.path.isfile(out):
            TTCollection(p, lazy=True).fonts[0].save(out)
        return out if os.path.isfile(out) else path
    except Exception:
        return path


def _from_fc_list():
    """fc-list 动态查询（按 zh 语言过滤，避免和西文字体混淆）。"""
    try:
        proc = subprocess.run(
            ['fc-list', ':lang=zh', '-f', '%{file}\n'],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return _best(proc.stdout.splitlines())


def _from_matplotlib():
    """从 matplotlib 已注册字体里找中文字体（主容器可能已经扫描过字体缓存）。"""
    try:
        from matplotlib import font_manager
        entries = font_manager.fontManager.ttflist
    except Exception:
        return None
    candidates = []
    for entry in entries:
        try:
            name = (entry.name or '').lower().replace(' ', '')
        except Exception:
            continue
        if any(key in name for key in _PREFERRED):
            candidates.append(entry.fname)
    return _best(candidates)


def _from_glob():
    candidates = []
    for pattern in _GLOB_PATTERNS:
        try:
            candidates.extend(glob.glob(pattern, recursive=True))
        except (OSError, ValueError):
            continue
    return _best(candidates)


def _first_existing(paths):
    for path in paths:
        if _is_font_file(path):
            return path
    return None


def find_cjk_font(use_cache=True):
    """返回可用的中文字体文件绝对路径；找不到返回 None。"""
    if use_cache and _cache['checked']:
        return _cache['path']
    path = (
        _from_env()
        or _from_bundled()
        or _from_fc_list()
        or _from_matplotlib()
        or _from_glob()
        or _first_existing(_FALLBACK_PATHS)
    )
    _cache['checked'] = True
    _cache['path'] = path
    return path


def reset_cache():
    """测试或部署方切换 LOBSTER_CJK_FONT 后强制重新查找。"""
    _cache['checked'] = False
    _cache['path'] = None
