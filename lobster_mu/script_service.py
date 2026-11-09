# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 脚本服务层（脚本 CRUD / LLM 生成 / 依赖安装 / 脚本执行，全部按 user_id 隔离）"""
import os
import re
import sys
import threading
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from lobster_mu.db import get_conn, BASE_DIR
from lobster_mu.paths import files_dir, gen_filename
from prompts import (
    SCRIPT_FIX_SYSTEM_PROMPT,
    SCRIPT_GENERATE_SYSTEM_PROMPT,
    SCRIPT_NAME_SYSTEM_PROMPT,
    build_script_fix_prompt,
    build_script_name_prompt,
)

# 项目根目录下的 packages/（pip --target 安装目标，全局共享）
PACKAGES_DIR = os.path.join(BASE_DIR, "packages")

# 允许的文件扩展名（安全白名单）
ALLOWED_FILE_EXTENSIONS = {'.pdf', '.txt', '.csv', '.json', '.xlsx', '.xls', '.docx', '.doc',
                           '.md', '.html', '.zip', '.rar', '.jpg', '.jpeg', '.png', '.gif',
                           '.pptx'}

# import名到pip包名的映射
IMPORT_TO_PIP = {
    'cv2': 'opencv-python',
    'PIL': 'Pillow',
    'bs4': 'beautifulsoup4',
    'sklearn': 'scikit-learn',
    'tensorflow': 'tensorflow',
    'torch': 'torch',
    'keras': 'keras',
    'matplotlib': 'matplotlib',
    'numpy': 'numpy',
    'pandas': 'pandas',
    'requests': 'requests',
    'flask': 'flask',
    'django': 'django',
    'sqlalchemy': 'sqlalchemy',
    'selenium': 'selenium',
    'pytest': 'pytest',
    'unittest': None,  # 内置模块
    'argparse': None,  # 内置模块
    'configparser': None,  # 内置模块
    'sqlite3': None,  # 内置模块
    'xml': None,  # 内置模块
    'fpdf': 'fpdf2',
    'docx': 'python-docx',
    'pptx': 'python-pptx',
    'yaml': 'PyYAML',
    'dateutil': 'python-dateutil',
    'dotenv': 'python-dotenv',
    'jwt': 'PyJWT',
    'Crypto': 'pycryptodome',
    'serial': 'pyserial',
    'magic': 'python-magic',
    'socks': 'PySocks',
    'fontTools': 'fonttools',
    'Levenshtein': 'python-Levenshtein',
}

# 依赖安装状态（每用户独立）：{user_id: state_dict}
_installation_state: Dict[int, Dict[str, Any]] = {}
# 全局锁：多用户并发 pip --target 会写坏 packages/，必须串行化
_install_lock = threading.Lock()

# 同一用户的脚本执行串行化锁：产物按"用户目录执行前后快照差"判定，
# 同用户并发执行（多会话同时跑脚本）会互相捡到对方刚生成的文件，
# 导致产物挂错会话。锁按 user_id 隔离，不影响不同用户并发。
_exec_locks: Dict[int, threading.Lock] = {}
_exec_locks_guard = threading.Lock()


def _get_exec_lock(user_id: int) -> threading.Lock:
    with _exec_locks_guard:
        return _exec_locks.setdefault(int(user_id or 0), threading.Lock())

# 沙箱镜像已预装的核心科学计算包（老 CPU 兼容版，见 sandbox/Dockerfile）。
# 这些包用户无需也不应自行安装——自行 pip 装最新版会拿到要求 X86_V2 的 wheel，
# 在老 CPU 服务器上 import 必崩。命中则直接拒绝并提示使用镜像内置版本。
PREINSTALLED_CORE_PACKAGES = {
    'numpy', 'scipy', 'pandas', 'matplotlib',
}


def _default_install_state() -> Dict[str, Any]:
    return {'in_progress': False, 'package': '', 'progress': 0, 'output': '', 'success': False}


def _get_default_llm_adapter(model_name: Optional[str] = None):
    """获取默认 LLM adapter（复制 lobster_claw.get_default_llm_adapter 逻辑）"""
    try:
        from engine.agent_worker import create_llm_adapter
        from models.model_manager import ModelManager

        model_manager = ModelManager()
        configured_models = [m for m in model_manager.get_all() if m.api_key and m.model_type == "text"]
        if not configured_models:
            return None

        if model_name:
            model = next((m for m in configured_models if m.model_name == model_name), None)
            if model:
                adapter = create_llm_adapter(model)
                return adapter

        model = configured_models[0]
        adapter = create_llm_adapter(model)
        return adapter
    except Exception as e:
        print(f"获取 LLM adapter 失败: {e}")
        return None


# Python 代码行的启发式特征：以这些前缀开头的行更可能是代码而非自然语言
_PY_LINE_PREFIXES = (
    'import ', 'from ', 'def ', 'class ', 'if ', 'elif ', 'else', 'for ', 'while ',
    'try:', 'except', 'finally', 'with ', 'return ', 'print(', 'break', 'continue',
    'pass', 'raise ', 'assert ', 'global ', 'nonlocal ', 'lambda ', 'yield',
    '#', '"""', "'''", '@', 'async ', 'await ',
)


def _detect_missing_modules(stderr: str) -> list:
    """从 stderr 中提取需要安装的模块名（缺包 / 包版本与沙箱 ABI 不匹配）。"""
    if not stderr:
        return []
    modules = set()
    # ModuleNotFoundError: No module named 'jieba' 或 No module named jieba
    for m in re.finditer(r"No module named '?([a-zA-Z_][a-zA-Z0-9_.]*)'?", stderr):
        mod = m.group(1).split('.')[0]
        modules.add(mod)
    # 二进制不兼容时不一定报 ModuleNotFoundError，可能只是子模块导不进来：
    # ImportError: cannot import name 'xxx' from 'cv2'
    for m in re.finditer(r"cannot import name '[^']+' from '?([a-zA-Z_][a-zA-Z0-9_.]*)'?", stderr):
        modules.add(m.group(1).split('.')[0])
    return sorted(modules)


# 沙箱镜像内的 Python 版本（见 sandbox/Dockerfile：python3.12）。
# 主容器是 python3.11，packages/ 里若残留主容器装的 cp311 二进制包，
# 沙箱内 import 会失败，且不一定报 ModuleNotFoundError（可能只报
# ImportError/undefined symbol），导致“以为装好了其实不可用”。
_SANDBOX_PY_VER = (3, 12)


def _sandbox_docker_mode() -> bool:
    """沙箱模式且 docker CLI 真实可用——此时执行环境是沙箱镜像而非主容器。"""
    try:
        import shutil
        from lobster_mu import sandbox as _sb
        return bool(_sb._CFG.enabled and _sb._CFG.mode == "docker" and shutil.which("docker"))
    except Exception:
        return False


def _wheel_tag_compatible(wheel_path: str) -> bool:
    """读取 dist-info/WHEEL 的 Tag，判断二进制包是否与沙箱 Python 版本匹配。"""
    try:
        with open(wheel_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except OSError:
        return True
    tags = re.findall(r'^Tag:\s*(\S+)', content, re.MULTILINE)
    if not tags:
        return True
    want = 'cp%d%d' % _SANDBOX_PY_VER
    for tag in tags:
        if tag.startswith('py3') or tag.startswith('py2.py3'):
            continue
        m = re.match(r'cp(\d)(\d+)', tag)
        if m and ('cp%s%s' % (m.group(1), m.group(2))) != want:
            return False
    return True


def _installed_in_packages(import_name: str) -> bool:
    """判断模块是否已装在共享 packages/（宿主机持久化目录，沙箱执行时复用）。

    只看目录/发行版元数据，不做 import——部分包是沙箱 python3.12 的二进制，
    主进程（3.11）import 会误判为缺失。返回 True 表示无需再次下载安装。
    沙箱模式下还会校验 WHEEL 标签：残留的主容器 cp311 包视作“未安装”，
    触发重装为 cp312 版本，避免出现“装了还是缺包”。
    """
    if not import_name:
        return False
    try:
        entries = os.listdir(PACKAGES_DIR)
    except OSError:
        return False
    lowered = {e.lower(): e for e in entries}
    name_l = import_name.lower()
    # 发行版名与 import 名可能不同（opencv-python -> cv2、Pillow -> PIL）
    pip_l = get_pip_package_name(import_name).lower().replace('-', '_')
    dist = next((v for k, v in lowered.items()
                 if k.startswith(pip_l + '-') and k.endswith('.dist-info')), None)
    if dist and _sandbox_docker_mode():
        if not _wheel_tag_compatible(os.path.join(PACKAGES_DIR, dist, 'WHEEL')):
            return False
    if name_l in lowered or f"{name_l}.py" in lowered:
        return True
    return bool(dist)


def _importable_here(import_name: str) -> bool:
    """主进程环境是否可导入（fallback=warn 直通执行时二者同环境，可据此跳过重复安装）。"""
    try:
        import importlib.util
        return importlib.util.find_spec(import_name) is not None
    except Exception:
        return False


# 沙箱镜像内可导入性探测缓存：{模块名: bool}
_sandbox_probe_cache: Dict[str, bool] = {}
_sandbox_probe_lock = threading.Lock()


def _sandbox_has_module(import_name: str) -> Optional[bool]:
    """在沙箱镜像内探测模块能否 import（结果缓存）。docker 不可用时返回 None。

    不能只看主进程能否 import：主容器/venv 装了 python-pptx 之类的包，不代表
    沙箱镜像里有（沙箱是独立镜像、独立 site-packages），这正是“明明装了还是缺包”
    的根因。这里直接开一个无网络短容器做 import 探测，只探 packages/ 里没有的包。
    """
    if not import_name:
        return False
    if not _sandbox_docker_mode():
        return None
    with _sandbox_probe_lock:
        cached = _sandbox_probe_cache.get(import_name)
    if cached is not None:
        return cached
    try:
        from lobster_mu import sandbox as _sb
        proc = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", _sb._CFG.image,
             "python3", "-c", f"import {import_name}"],
            capture_output=True, timeout=30,
        )
        ok = (proc.returncode == 0)
    except Exception:
        return None
    with _sandbox_probe_lock:
        _sandbox_probe_cache[import_name] = ok
    return ok


def _available_in_exec_env(import_name: str) -> bool:
    """模块在执行环境（沙箱或主进程）是否已可直接 import。"""
    probe = _sandbox_has_module(import_name)
    if probe is None:
        return _importable_here(import_name)
    return probe


_STDLIB_MODULES = set(getattr(sys, 'stdlib_module_names', ())) | set(sys.builtin_module_names)


def _scan_third_party_imports(code: str) -> List[str]:
    """静态扫描脚本里的 import，返回可能需要第三方安装的顶层模块名。"""
    if not code:
        return []
    names = set()
    for m in re.finditer(r'^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)', code, re.MULTILINE):
        names.add(m.group(1).split('.')[0])
    out = []
    for name in sorted(names):
        if name.startswith('_') or name in _STDLIB_MODULES:
            continue
        # IMPORT_TO_PIP 中显式为 None 的是内置模块
        if name in IMPORT_TO_PIP and IMPORT_TO_PIP[name] is None:
            continue
        if name.lower() in PREINSTALLED_CORE_PACKAGES:
            continue
        out.append(name)
    return out


def _ensure_dependencies(code: str, user_id: int, notify=None, log=None, attempted=None) -> List[str]:
    """执行前预检：把脚本用到但缺失的第三方库装进共享 packages/（宿主机持久化）。

    已安装过的包直接跳过——后续执行不再联网下载。安装过程逐行通过 log 回调
    推给前端；失败也通过 notify 提示，不再静默。attempted 会记录安装失败的
    import 名，避免执行后兜底再白跑一次网络安装。
    """
    missing = [
        name for name in _scan_third_party_imports(code)
        if not _installed_in_packages(name) and not _available_in_exec_env(name)
    ]
    notes = []
    for import_name in missing:
        pip_name = get_pip_package_name(import_name)
        if notify:
            notify(f"📦 检测到依赖 {import_name}，正在自动安装 {pip_name}…")
        result = install_dependency_sync(user_id, pip_name, on_output=log)
        if result.get('success'):
            notes.append(f"✅ 已自动安装依赖 {import_name}（{pip_name}）")
            if notify:
                notify(f"✅ {pip_name} 安装完成，后续执行无需再下载")
        else:
            reason = (result.get('message') or result.get('output') or '未知错误')
            notes.append(f"⚠️ 依赖 {import_name}（{pip_name}）自动安装失败：{str(reason)[:300]}")
            if attempted is not None:
                attempted.add(import_name)
            if notify:
                notify(f"❌ {pip_name} 自动安装失败：{str(reason)[:200]}")
    return notes


def _looks_like_python_line(line: str) -> bool:
    """判断一行是否像 Python 代码行（而非自然语言）。"""
    s = line.strip()
    if not s:
        return True  # 空行保留
    # 注释行
    if s.startswith('#'):
        return True
    # 字符串行开头
    if s.startswith(('"""', "'''", '"', "'")):
        return True
    # 以 Python 关键字/语句开头
    if s.startswith(_PY_LINE_PREFIXES):
        return True
    # 包含赋值、函数调用、属性访问、比较等代码特征
    if any(ch in s for ch in ('=', '(', ')', '[', ']', '{', '}', '.', ':', '+', '-', '*', '/', '%', '<', '>', '!', '&', '|', '^', '~', ',')):
        # 但排除纯中文句子（含中文标点且无英文标识符）
        if re.search(r'[，。！？；：""''（）【】]', s) and not re.search(r'[a-zA-Z_]\w*', s):
            return False
        return True
    return False


def _extract_python_from_text(content: str) -> Optional[str]:
    """从混合文本中提取 Python 代码行；若提取结果无法通过语法检查则返回 None。"""
    lines = content.split('\n')
    code_lines = [ln for ln in lines if _looks_like_python_line(ln)]
    candidate = '\n'.join(code_lines).strip()
    if not candidate:
        return None
    # 用语法检查验证提取结果是否为有效 Python
    try:
        compile(candidate, '<string>', 'exec')
        return candidate
    except SyntaxError:
        return None


def generate_script_code(requirements: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """根据用户需求调用LLM生成Python脚本代码，返回(脚本代码, 英文名称, 中文描述)"""
    try:
        adapter = _get_default_llm_adapter("shineyue")
        if not adapter:
            return None, None, None

        system_prompt = SCRIPT_GENERATE_SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户需求: {requirements}"}
        ]

        response = adapter.chat(messages)

        # 提取代码
        content = response.content if hasattr(response, 'content') else str(response)

        # 从markdown中提取代码
        code = None
        code_match = re.search(r'```python\n(.*?)```', content, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()

        if not code:
            code_match = re.search(r'```\n(.*?)```', content, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()

        # 兜底：未闭合的 ```python 围栏，取到末尾
        if not code:
            code_match = re.search(r'```python\n(.*)', content, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()

        if not code and content.strip():
            # 兜底：无代码围栏时，尝试从混合文本中提取 Python 代码行；
            # 若整段是自然语言（无任何 Python 特征），则返回 None 而不是把自然语言当代码
            code = _extract_python_from_text(content)

        if not code:
            return None, None, None

        # 字体样式/布局兜底：自定义中文字体未注册 B/I 变体、multi_cell 横向空间不足
        # 都会让 fpdf2 抛异常直接中断脚本
        code = _sanitize_pdf_code(code)

        # 调用LLM生成英文脚本名称和中文描述
        name_prompt = build_script_name_prompt(requirements, code)

        name_messages = [
            {"role": "system", "content": SCRIPT_NAME_SYSTEM_PROMPT},
            {"role": "user", "content": name_prompt}
        ]

        name_response = adapter.chat(name_messages)
        name_content = name_response.content if hasattr(name_response, 'content') else str(name_response)

        # 解析英文名称和中文描述
        script_name = "unnamed_script"
        script_desc = requirements[:50]

        name_match = re.search(r'ENGLISH_NAME:\s*(.+)', name_content)
        if name_match:
            script_name = name_match.group(1).strip()

        desc_match = re.search(r'CHINESE_DESC:\s*(.+)', name_content)
        if desc_match:
            script_desc = desc_match.group(1).strip()

        return code, script_name, script_desc

    except Exception as e:
        print(f"生成脚本代码失败: {e}")
        return None, None, None


def _extract_code_from_llm(content: str) -> Optional[str]:
    """从模型回复中提取 Python 代码（与 generate_script_code 同规则）。"""
    code = None
    m = re.search(r'```python\n(.*?)```', content, re.DOTALL)
    if m:
        code = m.group(1).strip()
    if not code:
        m = re.search(r'```\n(.*?)```', content, re.DOTALL)
        if m:
            code = m.group(1).strip()
    if not code:
        m = re.search(r'```python\n(.*)', content, re.DOTALL)
        if m:
            code = m.group(1).strip()
    if not code and content.strip():
        code = _extract_python_from_text(content)
    return code


_BUILTIN_FONT_FAMILIES = {"helvetica", "times", "courier", "symbol", "zapfdingbats", "arial"}

_FPDF_SET_FONT_STYLE_RE = re.compile(
    r"(set_font\s*\(\s*(?P<q1>['\"])(?P<family>[^'\"]+)(?P=q1)\s*,\s*)"
    r"(?P<q2>['\"])(?P<style>B|I|BI|IB)(?P=q2)"
)


def _sanitize_pdf_font_styles(code: str) -> str:
    """把自定义字体未注册的样式变体（B/I/BI）降级为常规样式。

    中文字体通常只注册一个常规字形，脚本里写 set_font('ChineseFont', 'B', 16)
    会让 fpdf2 抛 "Undefined font: chinesefontB" 并中断整个脚本；
    内置字体（helvetica/times/courier 等）本身支持样式，保持原样。
    """
    if not code or "set_font" not in code:
        return code

    def _repl(m):
        if m.group("family").strip().lower() in _BUILTIN_FONT_FAMILIES:
            return m.group(0)
        return m.group(1) + m.group("q2") + m.group("q2")

    try:
        return _FPDF_SET_FONT_STYLE_RE.sub(_repl, code)
    except Exception:
        return code


def _sanitize_pdf_layout(code: str) -> str:
    """在每处 multi_cell 前补一条 set_x(pdf.l_margin)，避免横向空间不足报错。

    fpdf2 在光标已靠近右边距时调用 multi_cell(0, ...) 会抛
    "Not enough horizontal space to render a single character" 并中断脚本，
    典型场景是 cell(...) 之后没有换行就直接 multi_cell。
    """
    if not code or "multi_cell" not in code:
        return code
    try:
        m = re.search(r"(\w+)\s*=\s*FPDF\s*\(", code)
        obj = m.group(1) if m else "pdf"
        pat = re.compile(r"^" + re.escape(obj) + r"\.multi_cell\(")
        out = []
        prev_sig = ""
        for line in code.split("\n"):
            stripped = line.strip()
            indent = line[:len(line) - len(line.lstrip())]
            if (stripped and pat.match(stripped) and "set_x(" not in prev_sig
                    and not prev_sig.endswith((",", "(", "[", "+"))):
                out.append(indent + obj + ".set_x(" + obj + ".l_margin)")
            out.append(line)
            if stripped:
                prev_sig = stripped
        return "\n".join(out)
    except Exception:
        return code


def _sanitize_pdf_code(code: str) -> str:
    return _sanitize_pdf_layout(_sanitize_pdf_font_styles(code))


def fix_script_code(code: str, error: str, requirements: str) -> Optional[str]:
    """执行报错后，把错误回喂模型修复脚本，返回修复后的完整代码（失败返回 None）。"""
    try:
        adapter = _get_default_llm_adapter("shineyue")
        if not adapter:
            return None

        prompt = build_script_fix_prompt(code, error, requirements)

        messages = [
            {"role": "system", "content": SCRIPT_FIX_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = adapter.chat(messages)
        content = response.content if hasattr(response, 'content') else str(response)
        fixed = _extract_code_from_llm(content)
        if fixed:
            fixed = _sanitize_pdf_code(fixed)
        return fixed or None
    except Exception as e:
        print(f"修复脚本代码失败: {e}")
        return None


def check_script_syntax(code: str) -> dict:
    """检查脚本语法是否正确"""
    try:
        compile(code, '<string>', 'exec')
        return {"success": True}
    except SyntaxError as e:
        return {"success": False, "error": f"{e.msg} (行 {e.lineno})\n\n{e.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def save_script_to_file(user_id: int, script_name: str, script_code: str) -> str:
    """保存脚本到该用户的产物目录，返回文件完整路径"""
    scripts_dir = files_dir(user_id)

    # 生成文件名（去除特殊字符）
    safe_name = re.sub(r'[\\/:*?"<>|]', '', script_name)
    if not safe_name:
        safe_name = "unnamed"

    # 检查文件名是否已存在，添加序号
    base_name = safe_name
    counter = 1
    while True:
        file_name = f"{safe_name}.py"
        file_path = os.path.join(scripts_dir, file_name)
        if not os.path.exists(file_path):
            break
        safe_name = f"{base_name}_{counter}"
        counter += 1

    # 写入文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(script_code)

    return file_path


# ============ 脚本库 CRUD（mu_scripts，按 user_id 隔离） ============

def _script_row_to_dict(row) -> dict:
    d = dict(row)
    d['is_approved'] = bool(d.get('is_approved'))
    return d


def create_script(user_id: int, name: str, code: str, description: str = '', is_approved: bool = False) -> int:
    """创建脚本，返回脚本 ID"""
    now = datetime.now().isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            '''INSERT INTO mu_scripts (user_id, name, code, description, is_approved, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (user_id, name, code, description, 1 if is_approved else 0, now, now)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_scripts(user_id: int) -> List[dict]:
    """列出该用户的全部脚本（按创建时间倒序）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            'SELECT * FROM mu_scripts WHERE user_id = ? ORDER BY created_at DESC, id DESC',
            (user_id,)
        ).fetchall()
        return [_script_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_script(user_id: int, script_id: int) -> Optional[dict]:
    """获取该用户的单个脚本"""
    conn = get_conn()
    try:
        row = conn.execute(
            'SELECT * FROM mu_scripts WHERE id = ? AND user_id = ?',
            (script_id, user_id)
        ).fetchone()
        return _script_row_to_dict(row) if row else None
    finally:
        conn.close()


def update_script(user_id: int, script_id: int, name: str = None, code: str = None,
                  description: str = None) -> bool:
    """更新脚本（仅更新传入字段），脚本不存在或越权返回 False"""
    script = get_script(user_id, script_id)
    if not script:
        return False

    now = datetime.now().isoformat()
    name = name if name is not None else script['name']
    code = code if code is not None else script['code']
    description = description if description is not None else script['description']

    conn = get_conn()
    try:
        conn.execute(
            'UPDATE mu_scripts SET name = ?, code = ?, description = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            (name, code, description, now, script_id, user_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_script(user_id: int, script_id: int) -> bool:
    """删除脚本，脚本不存在或越权返回 False"""
    if not get_script(user_id, script_id):
        return False

    conn = get_conn()
    try:
        conn.execute('DELETE FROM mu_scripts WHERE id = ? AND user_id = ?', (script_id, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def approve_script(user_id: int, script_id: int) -> bool:
    """审批脚本，允许执行包含危险操作的脚本"""
    if not get_script(user_id, script_id):
        return False

    now = datetime.now().isoformat()
    conn = get_conn()
    try:
        conn.execute(
            'UPDATE mu_scripts SET is_approved = 1, approved_at = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            (now, now, script_id, user_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def revoke_script(user_id: int, script_id: int) -> bool:
    """撤销脚本审批"""
    if not get_script(user_id, script_id):
        return False

    now = datetime.now().isoformat()
    conn = get_conn()
    try:
        conn.execute(
            'UPDATE mu_scripts SET is_approved = 0, approved_at = NULL, updated_at = ? WHERE id = ? AND user_id = ?',
            (now, script_id, user_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ============ 依赖检测与安装 ============

def get_pip_package_name(import_name: str) -> str:
    """将import名转换为pip包名"""
    return IMPORT_TO_PIP.get(import_name, import_name)


def detect_missing_dependencies(code: str) -> List[str]:
    """检测脚本中缺失的第三方依赖"""
    # packages 追加到 sys.path 末尾（补充而非覆盖系统包，避免用户不兼容包顶掉系统包）
    if PACKAGES_DIR not in sys.path:
        sys.path.append(PACKAGES_DIR)

    # 提取import语句中的包名
    import_patterns = [
        r'^import (\w+)',                    # import package
        r'^from (\w+) import',                # from package import
        r'^from (\w+)\.\w+ import',           # from package.sub import
    ]

    # 内置模块列表（不需要安装）
    builtin_modules = set(sys.builtin_module_names) | {
        'os', 'sys', 're', 'json', 'datetime', 'time', 'math',
        'random', 'collections', 'itertools', 'functools', 'threading',
        'subprocess', 'tempfile', 'pathlib', 'http', 'urllib', 'socket',
        'hashlib', 'base64', 'pickle', 'csv', 'logging', 'traceback',
        'typing', 'abc', 'enum', 'dataclasses', 'asyncio',
        'ssl', 'io', 'contextlib', 'warnings', 'statistics', 'numbers',
        'unittest', 'argparse', 'configparser', 'sqlite3', 'xml',
        'email', 'cgi', 'cgitb', 'getopt', 'getpass', 'glob', 'gzip',
        'io', 'ipaddress', 'json', 'keyword', 'linecache', 'locale',
        'msilib', 'netrc', 'nntplib', 'optparse', 'os', 'pathlib',
        'platform', 'plistlib', 'poplib', 'posix', 'pwd', 'py_compile',
        'pyclbr', 'pydoc', 'queue', 'quopri', 'random', 're', 'runpy',
        'sched', 'secrets', 'select', 'shlex', 'shutil', 'signal',
        'smtpd', 'smtplib', 'socket', 'socketserver', 'spwd', 'sqlite3',
        'ssl', 'statistics', 'string', 'struct', 'subprocess', 'sunau',
        'symbol', 'symtable', 'sys', 'sysconfig', 'tabnanny', 'tarfile',
        'telnetlib', 'tempfile', 'textwrap', 'threading', 'time',
        'timeit', 'trace', 'traceback', 'tracemalloc', 'tty', 'turtle',
        'types', 'typing', 'unicodedata', 'unittest', 'urllib', 'uu',
        'uuid', 'venv', 'warnings', 'wave', 'weakref', 'webbrowser',
        'winreg', 'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc',
        'zipapp', 'zipfile', 'zlib'
    }

    found_packages = set()

    for pattern in import_patterns:
        matches = re.findall(pattern, code, re.MULTILINE)
        for match in matches:
            found_packages.add(match)

    # 检测哪些包未安装
    missing = []
    for package in found_packages:
        if package in builtin_modules or IMPORT_TO_PIP.get(package) is None:
            continue
        # 核心科学计算包已由沙箱镜像预装，直接视为已满足，不提示用户安装
        if package.lower() in PREINSTALLED_CORE_PACKAGES:
            continue
        # 共享 packages/ 里已有（之前自动安装并持久化）→ 无需再次安装
        if _installed_in_packages(package):
            continue
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    return missing


def _install_to_packages_dir(user_id: int, package_name: str, on_output=None) -> Dict[str, Any]:
    """实际执行多镜像安装并更新该用户的安装状态（调用方需持有 _install_lock）"""
    state = _installation_state.setdefault(user_id, _default_install_state())

    # 拦截核心科学计算包：沙箱镜像已预装老 CPU 兼容版，用户无需自行安装。
    # （自行装最新版会拿到要求 X86_V2 的 wheel，老 CPU 上必崩）
    base = re.split(r'[<>=!~\s]', package_name.strip(), 1)[0].lower()
    if base in PREINSTALLED_CORE_PACKAGES:
        msg = (f'包 {base} 已由系统预装（兼容当前服务器 CPU 的版本），'
               f'无需安装，脚本中可直接 import 使用。')
        state.update({'in_progress': False, 'package': package_name, 'progress': 100,
                      'output': msg, 'success': False})
        return {'success': False, 'message': msg, 'output': msg}

    state.update({
        'in_progress': True,
        'package': package_name,
        'progress': 0,
        'output': '',
        'success': False
    })

    try:
        os.makedirs(PACKAGES_DIR, exist_ok=True)

        # 优先在沙箱镜像内安装：保证带 C 扩展的包（numpy/pandas 等）的 .so
        # 与执行环境（沙箱 python3.12）ABI 一致。
        # 注意：docker 模式下绝不回退主容器 pip——主容器是 python3.11，装出的
        # 二进制包在沙箱里 import 会失败，且会让“已安装”判断误报，导致反复缺包。
        sandbox_docker = False
        try:
            import shutil
            from lobster_mu import sandbox as _sb
            # 只有“沙箱模式+docker 真实可用”时才禁止回退主容器；
            # 本地开发（无 docker CLI）仍允许回退，否则连本地执行都装不上包
            sandbox_docker = bool(_sb._CFG.enabled and _sb._CFG.mode == "docker" and shutil.which("docker"))
        except Exception:
            pass
        try:
            from lobster_mu import sandbox
            ok, out = sandbox.install_dependency_in_sandbox(
                package_name, on_output=on_output
            )
            state['output'] = out or ''
            if ok:
                state['success'] = True
                state['progress'] = 100
                try:
                    import importlib
                    if PACKAGES_DIR not in sys.path:
                        sys.path.append(PACKAGES_DIR)
                    importlib.invalidate_caches()
                except Exception:
                    pass
                return {
                    'success': True,
                    'message': f'包 {package_name} 安装成功',
                    'output': out or ''
                }
            if sandbox_docker:
                # 沙箱模式下的安装失败必须如实上报客户端，不再回退主容器
                return {
                    'success': False,
                    'message': f'包 {package_name} 在沙箱内安装失败',
                    'output': out or '未知错误'
                }
            state['output'] = (out or '') + '\n[回退] 沙箱安装不可用，改用主容器安装...'
        except Exception as _e:
            if sandbox_docker:
                return {
                    'success': False,
                    'message': f'包 {package_name} 沙箱内安装异常: {_e}',
                    'output': str(_e)
                }
            state['output'] = f'[沙箱安装异常，回退本地] {_e}'

        # 使用多个国内镜像源加速安装，依次尝试
        mirror_sources = [
            ('https://pypi.tuna.tsinghua.edu.cn/simple', 'pypi.tuna.tsinghua.edu.cn'),
            ('https://mirrors.aliyun.com/pypi/simple/', 'mirrors.aliyun.com'),
            ('https://pypi.mirrors.ustc.edu.cn/simple/', 'pypi.mirrors.ustc.edu.cn'),
            ('https://pypi.douban.com/simple/', 'pypi.douban.com'),
        ]

        result = None
        last_error = None

        for index_url, trusted_host in mirror_sources:
            pip_args = [
                sys.executable, '-m', 'pip', 'install',
                '--target', PACKAGES_DIR,
                '--no-warn-script-location',
                '--index-url', index_url,
                '--trusted-host', trusted_host,
                package_name
            ]

            try:
                result = subprocess.run(
                    pip_args,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=600  # 大库安装需要较长超时
                )

                if result.returncode == 0:
                    break  # 安装成功，退出循环

                last_error = result.stderr
                state['output'] = f"镜像源 {index_url} 安装失败，尝试下一个...\n{result.stderr}"

            except subprocess.TimeoutExpired:
                last_error = f"镜像源 {index_url} 超时，尝试下一个..."
                state['output'] = last_error
                continue

        if result is None:
            # 所有镜像源都失败了
            state['output'] = f"所有镜像源安装失败: {last_error}"
            return {
                'success': False,
                'message': f'包 {package_name} 安装失败，所有镜像源均无法使用',
                'output': last_error or '未知错误'
            }

        state['output'] = result.stdout + result.stderr

        if result.returncode == 0:
            state['success'] = True
            state['progress'] = 100
            # 安装成功后刷新导入缓存 + 确保 packages 在 sys.path，
            # 否则同进程后续 detect_missing_dependencies 可能仍用旧目录快照误报“未安装”。
            try:
                import importlib
                if PACKAGES_DIR not in sys.path:
                    sys.path.append(PACKAGES_DIR)
                importlib.invalidate_caches()
            except Exception:
                pass
            return {
                'success': True,
                'message': f'包 {package_name} 安装成功',
                'output': result.stdout + result.stderr
            }
        else:
            return {
                'success': False,
                'message': f'包 {package_name} 安装失败',
                'output': result.stderr or result.stdout
            }
    except subprocess.TimeoutExpired:
        state['output'] = '安装超时'
        return {
            'success': False,
            'message': f'包 {package_name} 安装超时',
            'output': '安装超时（超过600秒）'
        }
    except Exception as e:
        state['output'] = str(e)
        return {
            'success': False,
            'message': f'包 {package_name} 安装出错: {str(e)}',
            'output': str(e)
        }
    finally:
        state['in_progress'] = False


def install_dependency_sync(user_id: int, package: str, on_output=None) -> dict:
    """同步安装Python包（多镜像依次尝试；全局锁串行化，防止多用户并发写坏 packages/）

    on_output：可选回调，实时接收 pip 安装输出行（用于前端展示安装过程）。
    """
    with _install_lock:
        return _install_to_packages_dir(user_id, package, on_output=on_output)


def install_dependency_async(user_id: int, package: str) -> dict:
    """异步安装指定的Python包（后台线程，状态按用户隔离）"""
    if not package:
        return {'success': False, 'error': '请提供包名'}

    # 立即置为进行中，避免状态查询窗口期返回旧数据
    state = _installation_state.setdefault(user_id, _default_install_state())
    state.update({
        'in_progress': True,
        'package': package,
        'progress': 0,
        'output': '',
        'success': False
    })

    threading.Thread(target=install_dependency_sync, args=(user_id, package), daemon=True).start()
    return {'success': True, 'message': f'正在后台安装包 {package}'}


def get_installation_status(user_id: int) -> dict:
    """获取该用户的依赖安装状态"""
    return dict(_installation_state.get(user_id, _default_install_state()))


# ============ 脚本执行 ============

def _decode_subprocess_output(data: bytes) -> str:
    """子进程输出解码：优先 utf-8，失败回退 gbk（Windows 中文环境）"""
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('gbk', errors='replace')


def pdf_is_blank(path: str) -> bool:
    """判断 PDF 是否是“空壳”（所有页面既无文字，也无任何可见图形）。

    典型场景：字体不含中文字形 / 脚本只建了空文件 / 正文写到了页面之外，
    文件能生成、不报错，但打开后一片空白。无法判定（缺 PyMuPDF 等）时返回
    False，宁可放过也不能误杀正常产物。
    """
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        with pymupdf.open(path) as doc:
            if doc.page_count <= 0:
                return True
            for page in doc:
                if page.get_text().strip():
                    return False
                pix = page.get_pixmap(dpi=20)
                samples = pix.samples
                stride = pix.n
                for i in range(0, len(samples), stride):
                    if stride >= 3:
                        if samples[i] < 245 or samples[i + 1] < 245 or samples[i + 2] < 245:
                            return False
                    elif samples[i] < 245:
                        return False
            return True
    except Exception:
        return False


def _open_pdf(path):
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    return pymupdf.open(path)


def pdf_page_count(path: str) -> int:
    """PDF 页数；无法解析时返回 0。"""
    try:
        with _open_pdf(path) as doc:
            return int(doc.page_count)
    except Exception:
        return 0


def render_pdf_page_png(path: str, page: int, dpi: int = 110) -> Optional[bytes]:
    """把 PDF 的某一页渲染成 PNG 字节流。

    服务端渲染用于前端预览：不依赖浏览器原生 PDF 插件，避免“预览空白但下载正常”。
    page 为 1 起始页码；越界或解析失败返回 None。
    """
    try:
        with _open_pdf(path) as doc:
            if page < 1 or page > doc.page_count:
                return None
            pix = doc[page - 1].get_pixmap(dpi=max(60, min(int(dpi), 200)))
            return pix.tobytes("png")
    except Exception:
        return None


def _collect_generated_files(work_dir: str, seen: set, blank_pdfs: Optional[List[str]] = None) -> List[dict]:
    """把 work_dir 中新增的白名单文件重命名归档；新名字记入 seen 防止重复收集。

    blank_pdfs: 传入列表时，检测到的空白 PDF 会被删除并把原始文件名记入该列表，
    由调用方判定为“生成失败”，避免向用户下发空白文件与虚假的下载链接。"""
    out = []
    try:
        entries = os.listdir(work_dir)
    except OSError:
        return out
    for entry in entries:
        entry_path = os.path.join(work_dir, entry)
        if not os.path.isfile(entry_path) or entry in seen:
            continue
        ext = os.path.splitext(entry)[1].lower()
        if ext not in ALLOWED_FILE_EXTENSIONS:
            continue
        try:
            size = os.path.getsize(entry_path)
        except OSError:
            continue
        if size <= 0:
            # 空文件视为生成失败（脚本只创建了句柄却没写入内容），不能当产物下发
            try:
                os.unlink(entry_path)
            except OSError:
                pass
            continue
        if ext == '.pdf' and pdf_is_blank(entry_path):
            try:
                os.unlink(entry_path)
            except OSError:
                pass
            if blank_pdfs is not None:
                blank_pdfs.append(entry)
            continue
        new_filename = gen_filename(entry)
        new_filepath = os.path.join(work_dir, new_filename)
        os.rename(entry_path, new_filepath)
        seen.add(new_filename)
        out.append({
            "name": new_filename,
            "original_name": entry,
            "size": size,
            "summary": _file_summary(new_filepath, new_filename),
            "download_url": f"/api/lobster-mu/script/files/download/{new_filename}"
        })
    return out


def _cleanup_residue(work_dir: str, seen: set) -> None:
    """删除 work_dir 中非白名单且未在 seen 里的残留文件（写回策略）。"""
    try:
        entries = os.listdir(work_dir)
    except OSError:
        return
    for entry in entries:
        entry_path = os.path.join(work_dir, entry)
        if not os.path.isfile(entry_path) or entry in seen:
            continue
        ext = os.path.splitext(entry)[1].lower()
        if ext not in ALLOWED_FILE_EXTENSIONS:
            try:
                os.unlink(entry_path)
            except OSError:
                pass


def execute_python_script(user_id: int, code: str, timeout: int = 60, status_cb=None) -> Dict[str, Any]:
    """执行Python脚本（按 user_id 隔离，spec §2.3 T6）。

    同一用户的执行串行化：产物按用户目录"执行前后快照差"收集，
    并发执行会把别的会话刚生成的文件误挂到本会话（产物串会话）。
    锁只包住沙箱执行与产物收集（通常秒级），模型生成等耗时环节不受影响。
    """
    with _get_exec_lock(user_id):
        return _execute_python_script_unlocked(user_id, code, timeout=timeout, status_cb=status_cb)


def _execute_python_script_unlocked(user_id: int, code: str, timeout: int = 60, status_cb=None) -> Dict[str, Any]:
    """脚本经沙箱执行器执行（user 角色走 Docker 沙箱，admin 直通），
    新生成文件重命名后归档到该用户目录，归档后清理非白名单残留。

    status_cb: 可选回调 fn(text)，在关键里程碑（开始执行/安装依赖/重试）上报状态，
    供 SSE 层把"后台正在运行"实时推给前端。"""
    def _notify(text):
        if status_cb:
            try:
                status_cb(text)
            except Exception:
                pass

    # pip 安装输出逐行推送（前端“执行过程”里可见下载/安装详情）
    _log_lines = [0]

    def _install_log(line):
        line = str(line or "").strip()
        if not line or _log_lines[0] >= 120:
            return
        # 只推送有价值的行，避免刷屏
        key = ("Collecting", "Downloading", "Using cached", "Installing collected",
               "Successfully installed", "Requirement already satisfied",
               "ERROR", "WARNING", "Looking in indexes", "Attempting uninstall",
               "Found existing installation", "Defaulting to user installation")
        if not any(k.lower() in line.lower() for k in key):
            return
        _log_lines[0] += 1
        if status_cb:
            try:
                status_cb({"stage": "install_log", "line": line[:300]})
            except Exception:
                pass

    _notify("⚙️ 正在执行脚本...")
    work_dir = files_dir(user_id)
    try:
        # 记录执行前目录中的文件
        before_files = set(os.listdir(work_dir))

        # packages/ 追加到当前进程 sys.path（补充系统包，不覆盖）
        if PACKAGES_DIR not in sys.path:
            sys.path.append(PACKAGES_DIR)

        # 执行前预检：脚本用到的第三方库若未装，先装进共享 packages/（宿主机持久化，
        # 后续执行直接复用，不再联网下载）；安装过程与失败原因都会推给前端
        _pre_failed = set()
        pre_notes = _ensure_dependencies(code, user_id, _notify, _install_log, _pre_failed)

        # 沙箱执行（spec T6）：替换原 subprocess.run(['python','-B',script_path])
        # 执行器会先把脚本原样归档到宿主机 data/scripts/<user_id>/ 再进沙箱运行
        from lobster_mu import sandbox

        def _run_once():
            return sandbox.get_executor(user_id).exec_script(
                code, user_id=user_id, timeout=timeout, work_dir=work_dir
            )

        def _output_of(result) -> str:
            out = (result.stdout or "") + (result.stderr or "")
            if not out:
                out = "脚本执行完成，无输出\n"
            if result.return_code != 0:
                out += f"\n(退出码: {result.return_code})"
            return out

        sr = _run_once()
        stdout_output = sr.stdout
        stderr_output = sr.stderr

        # 检测脚本执行后新生成的文件（白名单扩展名），重命名归档；
        # 空白 PDF 会被删除并记入 blank_pdfs，下面按“生成失败”处理
        blank_pdfs: List[str] = []
        generated_files = _collect_generated_files(work_dir, before_files, blank_pdfs)
        # 归档后残留清理（spec §4.1 写回策略）
        _cleanup_residue(work_dir, before_files)

        # 构建结果（沙箱级错误：不可用/超时/执行异常）
        if not sr.success and sr.error:
            return {
                "success": False,
                "result": f"❌ 脚本执行失败: {normalize_local_urls(sr.error)}\n",
                "generated_files": generated_files
            }

        result_str = _output_of(sr)
        dep_notes = list(pre_notes)

        # 执行后兜底：按 ModuleNotFoundError 自动补装依赖并重试（最多 3 轮，
        # 覆盖“装上 A 后运行才发现还缺 B”的链式缺失场景）。
        # 注意：这里不再用 packages/ 目录判断“已安装”——目录里可能有 ABI 不兼容的
        # 旧包（装了但沙箱导不进来），必须按运行时真实报错强制重装（--upgrade）。
        install_round = 0
        attempted = set(_pre_failed)
        while install_round < 3:
            missing = [
                m for m in _detect_missing_modules(stderr_output)
                if m not in attempted
            ]
            if not missing:
                break
            install_round += 1
            _notify(f"📦 检测到缺失依赖: {', '.join(missing)}，正在自动安装...")
            install_notes = []
            installed_ok = 0
            for mod in missing:
                attempted.add(mod)
                # import 名与 pip 包名可能不同（cv2→opencv-python、PIL→Pillow 等）
                pip_name = get_pip_package_name(mod)
                _notify(f"📦 正在安装依赖 {pip_name}（可能需要数十秒）...")
                install_result = install_dependency_sync(
                    user_id, pip_name, on_output=_install_log
                )
                if install_result.get('success'):
                    installed_ok += 1
                    install_notes.append(f"✅ 已自动安装 {mod}（{pip_name}）")
                    _notify(f"✅ {pip_name} 安装完成（已保留在沙箱环境，后续无需重新下载）")
                else:
                    reason = install_result.get('message') or install_result.get('output') or '未知错误'
                    tail = (install_result.get('output') or '').strip()[-500:]
                    install_notes.append(
                        f"❌ 安装 {pip_name} 失败: {str(reason)[:300]}"
                        + (("\n" + tail) if tail else "")
                    )
                    _notify(f"❌ {pip_name} 安装失败：{str(reason)[:200]}")

            if installed_ok == 0:
                result_str += "\n\n📦 检测到缺失依赖，但自动安装失败：\n" + "\n".join(install_notes)
                break

            dep_notes.extend(n for n in install_notes if n.startswith('✅'))
            _notify("🔄 依赖安装完成，重新执行脚本...")
            sr = _run_once()
            stdout_output = sr.stdout
            stderr_output = sr.stderr
            blank_pdfs = []
            generated_files.extend(_collect_generated_files(work_dir, before_files, blank_pdfs))
            _cleanup_residue(work_dir, before_files)
            result_str = _output_of(sr)
            if not (sr.success and sr.return_code == 0):
                result_str += f"\n❌ 第 {install_round} 轮依赖安装后重试仍失败"

        if dep_notes:
            result_str = "\n".join(dep_notes) + "\n\n" + result_str

        # 空白 PDF 不算成功：文件已删除、下载链接不会下发，并明确告知失败原因，
        # 避免“PDF 是空的但会话显示成功”
        blank_notes = ""
        if blank_pdfs and sr.success:
            blank_notes = ("❌ 生成的 PDF 内容为空（页面中没有任何文字或图形），"
                           "已删除空文件并判定为生成失败。"
                           "请确认脚本真的把正文写进了 PDF（add_page 后写入 multi_cell/cell），"
                           "且使用的中文字体包含汉字字形后重试。")

        # 失败时把 stderr 一并放到 error 字段，供上层（Agent 工具/前端）直接展示
        if sr.success and blank_pdfs:
            error_text = blank_notes
        else:
            error_text = "" if sr.success else (stderr_output or "")[:4000]

        return {
            "success": sr.success and not blank_pdfs,
            "result": normalize_local_urls(("\n\n".join(x for x in (result_str, blank_notes) if x)).strip()),
            "error": normalize_local_urls(error_text),
            "generated_files": generated_files
        }

    except SyntaxError as e:
        return {
            "success": False,
            "result": f"❌ 语法错误: {e.msg} (行 {e.lineno})\n\n{e.text}",
            "generated_files": []
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "result": f"❌ 执行错误: {str(e)}\n\n{traceback.format_exc()}",
            "generated_files": []
        }


# ============ 产物文件 ============

def _file_summary(filepath: str, filename: str) -> str:
    """生成文件内容简介（前端悬停提示用）：文本取开头预览，图片取尺寸，其它给类型。"""
    ext = os.path.splitext(filename)[1].lower()
    try:
        size = os.path.getsize(filepath)
    except OSError:
        return ""

    # 图片：尝试读取尺寸
    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'):
        try:
            from PIL import Image
            with Image.open(filepath) as im:
                w, h = im.size
            return f"图片（{w}×{h}）"
        except Exception:
            return "图片文件"

    # 文本类：取开头预览（只读少量字节，避免大文件开销）
    if ext in ('.txt', '.csv', '.json', '.md', '.html'):
        try:
            with open(filepath, 'rb') as f:
                head = f.read(512)
            text = head.decode('utf-8', errors='replace')
            text = re.sub(r'\s+', ' ', text).strip()
            if not text:
                return "（空文本文件）"
            return text[:120]
        except Exception:
            return ""

    return {
        '.pdf': "PDF 文档",
        '.docx': "Word 文档", '.doc': "Word 文档",
        '.xlsx': "Excel 表格", '.xls': "Excel 表格",
        '.pptx': "PPT 演示文稿",
        '.zip': "压缩包", '.rar': "压缩包",
    }.get(ext, "")


_LOCAL_URL_RE = re.compile(r'https?://(?:localhost|127\.0\.0\.1)(?::8888)?', re.IGNORECASE)


def normalize_local_urls(text: str) -> str:
    """把脚本输出中的本机绝对地址（http://localhost:8888 等）归一化为相对路径。

    脚本运行在隔离沙箱中，硬编码的 localhost 地址在服务器部署后不可达；
    去掉 scheme+host 后前端会按当前站点 origin 解析，链接仍然可用。
    """
    if not text:
        return text
    return _LOCAL_URL_RE.sub('', text)


def _file_entry(work_dir: str, filename: str) -> Optional[Dict[str, Any]]:
    """构建单个产物文件条目；不符合白名单扩展名、不是文件或空文件时返回 None"""
    filepath = os.path.join(work_dir, filename)
    if not os.path.isfile(filepath):
        return None
    if os.path.splitext(filename)[1].lower() not in ALLOWED_FILE_EXTENSIONS:
        return None
    try:
        size = os.path.getsize(filepath)
    except OSError:
        return None
    if size <= 0:
        # 空文件不是有效产物，不能生成下载链接
        return None
    return {
        "name": filename,
        "size": size,
        "created_at": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat(),
        "summary": _file_summary(filepath, filename),
        "download_url": f"/api/lobster-mu/script/files/download/{filename}"
    }


def list_generated_files(user_id: int) -> List[Dict[str, Any]]:
    """列出该用户产物目录下的全部文件（白名单扩展名，按创建时间倒序）"""
    work_dir = files_dir(user_id)
    files = []
    if os.path.exists(work_dir):
        for filename in os.listdir(work_dir):
            entry = _file_entry(work_dir, filename)
            if entry:
                files.append(entry)

    files.sort(key=lambda x: x["created_at"], reverse=True)
    return files


def snapshot_generated_names(user_id: int) -> set:
    """轻量快照：当前产物文件名集合（不读文件内容，用于对比"本轮新增了哪些文件"）"""
    work_dir = files_dir(user_id)
    if not os.path.exists(work_dir):
        return set()
    names = set()
    for filename in os.listdir(work_dir):
        if os.path.splitext(filename)[1].lower() in ALLOWED_FILE_EXTENSIONS:
            if os.path.isfile(os.path.join(work_dir, filename)):
                names.add(filename)
    return names


def build_file_entries(user_id: int, names) -> List[Dict[str, Any]]:
    """按文件名构建产物条目（结构与 list_generated_files 一致，仅对指定文件读摘要）"""
    work_dir = files_dir(user_id)
    entries = []
    for filename in names:
        entry = _file_entry(work_dir, filename)
        if entry:
            entries.append(entry)
    return entries


def is_valid_artifact(user_id: int, filename: str) -> bool:
    """产物文件是否真实存在且非空（下载链接只有在文件确实生成时才有效）。"""
    name = os.path.basename(str(filename or ""))
    if not name:
        return False
    path = os.path.join(files_dir(user_id), name)
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def filter_existing_files(user_id: int, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """过滤掉不存在或空文件的产物条目，避免把无效下载链接下发给用户。"""
    out = []
    for f in files or []:
        if not isinstance(f, dict):
            continue
        if is_valid_artifact(user_id, f.get("name")):
            out.append(f)
    return out


_DOWNLOAD_LINK_RE = re.compile(r"/api/lobster-mu/script/files/download/([^\s)?\]\)>\"']+)")
_FILE_BLOCK_HEADING_RE = re.compile(r"^\s*[-*]?\s*📎.*生成的文件")


def _line_links_dead(user_id: int, line: str) -> Optional[bool]:
    """判断一行中的产物下载链接是否全部指向不存在/空文件；无链接返回 None。"""
    names = _DOWNLOAD_LINK_RE.findall(line)
    if not names:
        return None
    from urllib.parse import unquote
    return not any(is_valid_artifact(user_id, unquote(n)) for n in names)


def strip_invalid_download_links(user_id: int, text: str) -> str:
    """删除引用了不存在产物的下载链接行（模型自行编造的文件名+下载地址）。

    只处理本平台产物下载链接：整行移除"死链"；若"📎 ...生成的文件"标题下
    已没有任何有效链接，则连标题一起移除。其余内容原样保留。
    """
    if not text:
        return text
    lines = text.split("\n")
    kept = []
    for line in lines:
        if _line_links_dead(user_id, line):
            continue
        kept.append(line)

    # 清理空掉的文件块标题（标题后到下个空行之间没有有效下载链接）
    result = []
    i = 0
    while i < len(kept):
        line = kept[i]
        if _FILE_BLOCK_HEADING_RE.match(line):
            j = i + 1
            has_link = False
            while j < len(kept) and kept[j].strip():
                if _DOWNLOAD_LINK_RE.search(kept[j]):
                    has_link = True
                    break
                j += 1
            if not has_link:
                # 标题下没有有效链接：连同其上方紧邻的分隔线（及中间空行）一起移除
                k = len(result) - 1
                while k >= 0 and not result[k].strip():
                    k -= 1
                if k >= 0 and result[k].strip() in ("---", "***", "___"):
                    del result[k:]
                i += 1
                continue
        result.append(line)
        i += 1
    return "\n".join(result)


def delete_generated_file(user_id: int, file_name: str) -> bool:
    """删除用户产物文件：复用 get_generated_file_path 的路径白名单校验，防止越权删除。"""
    path = get_generated_file_path(user_id, file_name)  # 非法/不存在时抛 ValueError
    try:
        os.remove(path)
        return True
    except OSError as e:
        logger.warning("删除产物文件失败 %s: %s", path, e)
        return False


def get_generated_file_path(user_id: int, file_name: str) -> str:
    """解析用户产物文件完整路径：必须落在 files_dir(user_id) 内，否则抛 ValueError"""
    work_dir = os.path.abspath(files_dir(user_id))
    safe_name = os.path.basename(file_name or "")
    if not safe_name or safe_name in ('.', '..'):
        raise ValueError(f"非法文件名: {file_name}")

    resolved = os.path.abspath(os.path.join(work_dir, safe_name))
    if resolved != work_dir and not resolved.startswith(work_dir + os.sep):
        raise ValueError(f"路径越权访问: {file_name}")
    if not os.path.isfile(resolved):
        raise ValueError(f"文件不存在: {file_name}")
    return resolved
