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
}

# 依赖安装状态（每用户独立）：{user_id: state_dict}
_installation_state: Dict[int, Dict[str, Any]] = {}
# 全局锁：多用户并发 pip --target 会写坏 packages/，必须串行化
_install_lock = threading.Lock()


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


def generate_script_code(requirements: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """根据用户需求调用LLM生成Python脚本代码，返回(脚本代码, 英文名称, 中文描述)"""
    try:
        adapter = _get_default_llm_adapter("shineyue")
        if not adapter:
            return None, None, None

        system_prompt = """你是一个专业的Python脚本生成器。请根据用户的需求，生成一个完整、可运行的Python脚本。

要求：
1. 只返回Python代码，不要包含任何解释性文字
2. 代码必须完整，可以直接运行
3. 如果需要输出结果，请使用print()函数
4. 代码应该简洁明了，遵循Python最佳实践
5. 如果需要使用外部库，请在代码中添加注释说明
特殊能力 - 生成中文PDF文档：
当用户需要生成PDF文档时，请使用fpdf2库生成。系统已安装fpdf2库，支持中文显示。
生成PDF的代码模板如下：

```python
from fpdf import FPDF
import os

# 创建PDF对象
pdf = FPDF()
pdf.add_page()

# 注册中文字体（系统会自动查找微软雅黑、宋体等中文字体）
font_paths = [
    'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
    'C:/Windows/Fonts/simsun.ttc',    # 宋体
    'C:/Windows/Fonts/simhei.ttf',    # 黑体
]
font_path = None
for fp in font_paths:
    if os.path.exists(fp):
        font_path = fp
        break

if font_path:
    pdf.add_font('ChineseFont', '', font_path, uni=True)
    pdf.set_font('ChineseFont', '', 12)
else:
    pdf.set_font('Arial', '', 12)

# 设置标题
pdf.set_font('ChineseFont' if font_path else 'Arial', '', 18)
pdf.cell(0, 20, '文档标题', ln=True, align='C')

# 设置正文
pdf.set_font('ChineseFont' if font_path else 'Arial', '', 12)
pdf.ln(10)
pdf.multi_cell(0, 10, '这是正文内容')
pdf.ln(5)

# 保存文件
pdf.output('output.pdf')
print("PDF已生成: output.pdf")
```

注意：生成PDF时务必注册中文字体，否则中文会显示为乱码。"""

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

        if not code and content.strip():
            code = content.strip()

        if not code:
            return None, None, None

        # 调用LLM生成英文脚本名称和中文描述
        name_prompt = f"""根据以下Python脚本和用户需求，生成一个简短的英文脚本名称（用下划线连接单词，如 hello_world、check_system_info）和一句中文描述。

用户需求: {requirements}

脚本代码:
```python
{code}
```

请按以下格式返回（不要包含其他内容）:
ENGLISH_NAME: 英文脚本名称
CHINESE_DESC: 中文描述"""

        name_messages = [
            {"role": "system", "content": "你是一个命名助手，请严格按照格式返回。"},
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
    # 添加packages目录到sys.path，确保能检测到安装的包
    if PACKAGES_DIR not in sys.path:
        sys.path.insert(0, PACKAGES_DIR)

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
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    return missing


def _install_to_packages_dir(user_id: int, package_name: str) -> Dict[str, Any]:
    """实际执行多镜像安装并更新该用户的安装状态（调用方需持有 _install_lock）"""
    state = _installation_state.setdefault(user_id, _default_install_state())

    state.update({
        'in_progress': True,
        'package': package_name,
        'progress': 0,
        'output': '',
        'success': False
    })

    try:
        os.makedirs(PACKAGES_DIR, exist_ok=True)

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


def install_dependency_sync(user_id: int, package: str) -> dict:
    """同步安装Python包（多镜像依次尝试；全局锁串行化，防止多用户并发写坏 packages/）"""
    with _install_lock:
        return _install_to_packages_dir(user_id, package)


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


def execute_python_script(user_id: int, code: str, timeout: int = 60) -> Dict[str, Any]:
    """执行Python脚本（按 user_id 隔离）：脚本写入该用户产物目录后以 python -B 执行，
    packages/ 注入 sys.path 与 PYTHONPATH，新生成文件重命名后归档到该用户目录。"""
    work_dir = files_dir(user_id)
    script_path = os.path.join(work_dir, gen_filename("script.py"))
    try:
        # 脚本先写到用户产物目录再执行
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(code)

        # 设置环境变量，确保子进程使用UTF-8编码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'

        # packages/ 注入当前进程 sys.path，保证已安装包可被导入
        if PACKAGES_DIR not in sys.path:
            sys.path.insert(0, PACKAGES_DIR)

        # 设置PYTHONPATH环境变量，供子进程使用
        current_pythonpath = env.get('PYTHONPATH', '')
        if current_pythonpath:
            env['PYTHONPATH'] = PACKAGES_DIR + os.pathsep + current_pythonpath
        else:
            env['PYTHONPATH'] = PACKAGES_DIR

        # 记录执行前目录中的文件（脚本文件本身已包含在内）
        before_files = set(os.listdir(work_dir))

        # 使用subprocess执行脚本，捕获输出
        proc = subprocess.run(
            ['python', '-B', script_path],
            capture_output=True,
            timeout=timeout,
            cwd=work_dir,
            env=env
        )
        stdout_output = _decode_subprocess_output(proc.stdout or b'')
        stderr_output = _decode_subprocess_output(proc.stderr or b'')

        # 检测脚本执行后新生成的文件（白名单扩展名），重命名归档
        generated_files = []
        for entry in os.listdir(work_dir):
            entry_path = os.path.join(work_dir, entry)
            if os.path.isfile(entry_path) and entry not in before_files:
                ext = os.path.splitext(entry)[1].lower()
                if ext in ALLOWED_FILE_EXTENSIONS:
                    new_filename = gen_filename(entry)
                    new_filepath = os.path.join(work_dir, new_filename)
                    os.rename(entry_path, new_filepath)

                    generated_files.append({
                        "name": new_filename,
                        "original_name": entry,
                        "size": os.path.getsize(new_filepath),
                        "download_url": f"/api/lobster-mu/script/files/download/{new_filename}"
                    })

        # 构建结果
        result_str = ""
        if stdout_output:
            result_str += stdout_output
        if stderr_output:
            result_str += stderr_output
        if not stdout_output and not stderr_output:
            result_str += "脚本执行完成，无输出\n"

        return {
            "success": True,
            "result": result_str,
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
    finally:
        try:
            if os.path.exists(script_path):
                os.unlink(script_path)
        except OSError:
            pass


# ============ 产物文件 ============

def list_generated_files(user_id: int) -> List[Dict[str, Any]]:
    """列出该用户产物目录下的全部文件（白名单扩展名，按创建时间倒序）"""
    work_dir = files_dir(user_id)
    files = []
    if os.path.exists(work_dir):
        for filename in os.listdir(work_dir):
            filepath = os.path.join(work_dir, filename)
            if os.path.isfile(filepath):
                ext = os.path.splitext(filename)[1].lower()
                if ext in ALLOWED_FILE_EXTENSIONS:
                    files.append({
                        "name": filename,
                        "size": os.path.getsize(filepath),
                        "created_at": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat(),
                        "download_url": f"/api/lobster-mu/script/files/download/{filename}"
                    })

    files.sort(key=lambda x: x["created_at"], reverse=True)
    return files


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
