# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 工具层（execute_tool_call / web_search / 操作日志，全部按 user_id 隔离）"""
import os
import re
import sys
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from lobster_mu.db import get_conn, BASE_DIR
from lobster_mu.paths import resolve_user_path, files_dir
from lobster_mu import script_service

# 危险命令黑名单
DANGEROUS_COMMANDS = [
    "rm", "del", "erase", "format", "shutdown", "reboot", "poweroff",
    "mkfs", "fdisk", "diskpart", "chkdsk", "sfc", "regedit",
    "taskkill", "kill", "pkill", "systemctl", "service",
    "rmdir", "rd", "md", "mkdir", "move", "copy", "xcopy",
    "attrib", "cacls", "icacls", "takeown",
    "curl", "wget", "powershell", "cmd", "bash", "python",
    "node", "npm", "pip", "git", "svn", "hg",
    "sudo", "su", "chmod", "chown", "apt", "yum", "dnf",
    "apt-get", "rpm", "dpkg", "brew", "aptitude", "pacman"
]

# 允许执行的命令白名单
ALLOWED_COMMANDS = [
    "echo", "dir", "ls", "type", "cat", "find", "grep",
    "date", "time", "whoami", "hostname", "ver", "uname",
    "ping", "tracert", "nslookup", "ipconfig", "ifconfig",
    "netstat", "tasklist", "ps", "tree", "cd", "pwd",
    "cls", "clear", "sort", "more", "less", "head", "tail",
    "wc", "uniq", "sort", "cut", "paste", "split", "join"
]


# ============ 操作审计日志（mu_operation_logs） ============

def log_operation(user_id: int, operation: str, detail: str = '', success: bool = True,
                  ip: str = '', error: str = ''):
    """写入操作审计日志；日志失败不影响主流程"""
    if error:
        detail = f'{detail} | 错误: {error}' if detail else error
    try:
        conn = get_conn()
        try:
            conn.execute(
                'INSERT INTO mu_operation_logs (user_id, operation, detail, success, ip, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, operation, detail, 1 if success else 0, ip, datetime.now().isoformat())
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


# ============ 命令执行 ============

def is_command_safe(command: str) -> bool:
    cmd_lower = command.lower().strip()
    for dangerous in DANGEROUS_COMMANDS:
        if cmd_lower.startswith(dangerous) or dangerous in cmd_lower.split():
            return False
    return True


def execute_shell_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    """执行shell命令（同步实现，语义与原版一致，输出按 utf-8 解码）"""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            cwd=str(BASE_DIR)
        )
        return {
            "success": True,
            "stdout": proc.stdout.decode('utf-8', errors='replace'),
            "stderr": proc.stderr.decode('utf-8', errors='replace'),
            "return_code": proc.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"命令执行超时（{timeout}秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def exec_cmd(command: str) -> str:
    """exec 工具：危险命令黑名单 + 允许命令白名单双重校验后执行"""
    if not command or not command.strip():
        return "❌ 命令不能为空"
    cmd_lower = command.strip().lower().split()[0]
    if cmd_lower in DANGEROUS_COMMANDS:
        return f"❌ 危险命令禁止执行: {cmd_lower}"
    if cmd_lower not in ALLOWED_COMMANDS:
        return f"❌ 命令不在允许列表中: {cmd_lower}"
    if not is_command_safe(command):
        return "❌ 安全警告：该命令不在白名单中，禁止执行"

    result = execute_shell_command(command, timeout=30)
    if not result.get("success"):
        return f"❌ 命令执行失败: {result.get('error', '未知错误')}"

    output = ""
    if result.get("stdout"):
        output += f"标准输出:\n{result['stdout']}\n"
    if result.get("stderr"):
        output += f"错误输出:\n{result['stderr']}\n"
    if result.get("return_code") != 0:
        output += f"返回码: {result['return_code']}"
    if not output:
        output = "命令执行完成，无输出"
    return f"```bash\n{command}\n```\n\n执行结果:\n{output}"


# ============ 文件类工具（路径均经 resolve_user_path 按 user_id 校验） ============

def read_file(path: str, user_id: int) -> str:
    try:
        file_path = resolve_user_path(user_id, path, write=False)
    except ValueError:
        return f"❌ 无权访问该文件: {path}"
    try:
        if not os.path.isfile(file_path):
            return f"❌ 文件不存在: {path}"
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return f"```\n{content}\n```"
    except Exception as e:
        return f"❌ 读取文件失败: {str(e)}"


def write_file(path: str, content: str, user_id: int) -> str:
    try:
        file_path = resolve_user_path(user_id, path, write=True)
    except ValueError:
        return f"❌ 无权写入该文件: {path}"
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✅ 文件写入成功: {path}"
    except Exception as e:
        return f"❌ 写入文件失败: {str(e)}"


def list_dir(path: str, user_id: int) -> str:
    try:
        dir_path = resolve_user_path(user_id, path or ".", write=False)
    except ValueError:
        return f"❌ 无权访问该目录: {path}"
    try:
        if not os.path.isdir(dir_path):
            return f"❌ 目录不存在: {path}"
        items = []
        for item in sorted(os.listdir(dir_path)):
            item_path = os.path.join(dir_path, item)
            if os.path.isfile(item_path):
                items.append(f"📄 {item} ({os.path.getsize(item_path)} bytes)")
            elif os.path.isdir(item_path):
                items.append(f"📁 {item}/")
        return "\n".join(items) if items else "目录为空"
    except Exception as e:
        return f"❌ 列出目录失败: {str(e)}"


def edit_file(path: str, old_text: str, new_text: str, user_id: int) -> str:
    try:
        file_path = resolve_user_path(user_id, path, write=True)
    except ValueError:
        return f"❌ 无权编辑该文件: {path}"
    try:
        if not os.path.isfile(file_path):
            return f"❌ 文件不存在: {path}"
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_text not in content:
            return "❌ 未找到要替换的文本"
        new_content = content.replace(old_text, new_text)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return f"✅ 文件编辑成功: {path}"
    except Exception as e:
        return f"❌ 编辑文件失败: {str(e)}"


def apply_patch(patches: List[Dict[str, Any]], user_id: int) -> str:
    """批量应用文本补丁（每个补丁的路径均按 user_id 校验）"""
    changes_made = 0
    errors = []

    for patch in patches or []:
        path = patch.get("path", "")
        old_text = patch.get("old_text", "")
        new_text = patch.get("new_text", "")

        if not path or not old_text:
            errors.append(f"补丁参数不完整: {path}")
            continue

        result = edit_file(path, old_text, new_text, user_id)
        if result.startswith("✅"):
            changes_made += 1
        else:
            errors.append(f"{path}: {result}")

    summary = f"补丁应用完成，成功 {changes_made} 个文件"
    if errors:
        return f"⚠️ {summary}\n错误:\n" + "\n".join(errors)
    return f"✅ {summary}"


# ============ 网络类工具 ============

def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    try:
        import httpx
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=headers or {})
        content = resp.text[:10000]
        return f"✅ HTTP GET {url}\n状态码: {resp.status_code}\n\n{content}"
    except Exception as e:
        return f"❌ HTTP GET 失败: {str(e)}"


def http_post(url: str, headers: Optional[Dict[str, str]] = None,
              data: Optional[Dict[str, Any]] = None) -> str:
    try:
        import httpx
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers or {}, json=data or {})
        content = resp.text[:10000]
        return f"✅ HTTP POST {url}\n状态码: {resp.status_code}\n\n{content}"
    except Exception as e:
        return f"❌ HTTP POST 失败: {str(e)}"


def browse(url: str, timeout: int = 30) -> str:
    try:
        import httpx
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
        title_match = re.search(r'<title>(.*?)</title>', resp.text, re.IGNORECASE)
        title = title_match.group(1) if title_match else "无标题"
        return f"✅ 已浏览 {url}\n标题: {title}\n状态码: {resp.status_code}\n内容长度: {len(resp.text)}"
    except Exception as e:
        return f"❌ 浏览失败: {str(e)}"


def screenshot(url: str, timeout: int = 30, user_id: int = 0) -> str:
    """网页截图：保存到该用户产物目录并返回下载链接"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--window-size=1920,1080')

        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.set_page_load_timeout(timeout)
            driver.get(url)
            png_bytes = driver.get_screenshot_as_png()
        finally:
            driver.quit()

        from lobster_mu.paths import gen_filename
        filename = gen_filename("screenshot.png")
        filepath = os.path.join(files_dir(user_id), filename)
        with open(filepath, 'wb') as f:
            f.write(png_bytes)

        download_url = f"/api/lobster-mu/script/files/download/{filename}"
        return f"✅ 截图成功: {url}\n尺寸: 1920x1080\n📄 文件名: {filename}\n📥 下载链接: {download_url}"
    except ImportError:
        return "❌ 截图失败: 未安装 selenium，请先安装依赖（pip install selenium）"
    except Exception as e:
        return f"❌ 截图失败: {str(e)}"


def web_search(query: str, num_results: int = 5) -> str:
    try:
        from search.search_manager import SearchManager
        search_manager = SearchManager()
        results = search_manager.search_sync(query, num_results=num_results)
        if not results:
            return "❌ 搜索无结果"
        output = []
        for i, result in enumerate(results, 1):
            if isinstance(result, dict):
                title = result.get("title", "")
                url = result.get("url", "")
                snippet = result.get("content", result.get("snippet", ""))[:200]
            else:
                title = getattr(result, "title", "")
                url = getattr(result, "url", "")
                snippet = getattr(result, "snippet", "")[:200]
            output.append(f"{i}. **{title}**")
            output.append(f"   URL: {url}")
            output.append(f"   摘要: {snippet}...")
            output.append("")
        return "\n".join(output)
    except Exception as e:
        return f"❌ 搜索失败: {str(e)}"


# ============ PDF 生成（fpdf2，中文字体查找逻辑照抄源码） ============

def _tool_generate_pdf(content: str, user_id: int) -> str:
    title = "文档"

    # 从内容中提取标题
    lines = content.split('\n')
    if lines:
        first_line = lines[0].strip()
        # 如果第一行较短，可能是标题
        if len(first_line) < 30 and len(lines) > 1:
            title = first_line
            content = '\n'.join(lines[1:]).strip()

    try:
        # 检查fpdf2是否安装，未安装则自动安装到项目 packages/
        try:
            import fpdf
        except ImportError:
            packages_dir = script_service.PACKAGES_DIR
            os.makedirs(packages_dir, exist_ok=True)

            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--target', packages_dir,
                 '--index-url', 'https://pypi.tuna.tsinghua.edu.cn/simple',
                 '--trusted-host', 'pypi.tuna.tsinghua.edu.cn', 'fpdf2'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=120
            )

            if packages_dir not in sys.path:
                sys.path.insert(0, packages_dir)

        from fpdf import FPDF

        def find_chinese_font():
            font_paths = [
                'C:/Windows/Fonts/msyh.ttc',
                'C:/Windows/Fonts/simsun.ttc',
                'C:/Windows/Fonts/simhei.ttf',
                'C:/Windows/Fonts/kaiu.ttf',
                'C:/Windows/Fonts/arialuni.ttf',
                '/Library/Fonts/Noto Sans CJK SC.ttc',
                '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            ]
            for font_path in font_paths:
                if os.path.exists(font_path):
                    return font_path
            return None

        font_path = find_chinese_font()
        pdf = FPDF()
        pdf.add_page()

        if font_path:
            font_name = 'ChineseFont'
            pdf.add_font(font_name, '', font_path, uni=True)
            pdf.set_font(font_name, '', 12)
        else:
            font_name = 'Arial'

        pdf.set_font(font_name, '', 18)
        pdf.cell(0, 20, title, ln=True, align='C')
        pdf.set_font(font_name, '', 12)
        pdf.ln(10)

        paragraphs = content.split('\n')
        for para in paragraphs:
            para = para.strip()
            if para:
                pdf.multi_cell(0, 12, para, align='L')
                pdf.ln(5)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"document_{timestamp}.pdf"
        filepath = os.path.join(files_dir(user_id), filename)
        pdf.output(filepath)

        download_url = f"/api/lobster-mu/script/files/download/{filename}"

        return (f"✅ PDF文件已生成！\n\n📄 文件名: {filename}\n📝 标题: {title}\n"
                f"📥 下载链接: http://localhost:8888{download_url}\n"
                f"🔤 使用字体: {font_path if font_path else 'Arial (无中文字体)'}")

    except ImportError:
        return "❌ PDF生成失败: 未安装 fpdf2 且自动安装失败，请先执行 pip install fpdf2 后重试"
    except Exception as e:
        return f"❌ PDF生成失败: {str(e)}"


# ============ 脚本类工具（委托 script_service，传 user_id） ============

def _tool_script_create(code: str, user_id: int) -> str:
    # 调用LLM生成脚本代码、英文名称和中文描述
    script_code, script_name, script_desc = script_service.generate_script_code(code)

    if not script_code:
        return "❌ 脚本生成失败，请重试"

    # 检查语法
    syntax_result = script_service.check_script_syntax(script_code)

    if syntax_result["success"]:
        # 保存到文件系统和脚本库
        script_service.save_script_to_file(user_id, script_name, script_code)
        script_service.create_script(user_id, script_name, script_code,
                                     description=script_desc, is_approved=True)

        # 执行并返回结果
        exec_result = script_service.execute_python_script(user_id, script_code)
        return exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
    else:
        return f"❌ 脚本语法错误:\n\n{syntax_result['error']}\n\n请修改需求后重新尝试。"


def _tool_script_execute(script_id, code: str, user_id: int) -> str:
    if script_id:
        script = script_service.get_script(user_id, script_id)
        if script:
            exec_result = script_service.execute_python_script(user_id, script["code"])
            return exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
        else:
            return f"❌ 脚本不存在，ID: {script_id}"
    elif code:
        exec_result = script_service.execute_python_script(user_id, code)
        return exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
    else:
        return "❌ 请提供脚本ID或脚本代码"


def _tool_script_list(user_id: int) -> str:
    scripts = script_service.list_scripts(user_id)
    if not scripts:
        return "📋 暂无脚本"
    result = "📋 脚本列表:\n"
    for script in scripts:
        result += (f"\nID: {script['id']}\n名称: {script['name']}\n"
                   f"描述: {script.get('description', '无')}\n"
                   f"创建时间: {script['created_at'][:19].replace('T', ' ')}\n")
    return result


# ============ 工具调度入口 ============

def _op_detail(tool: str, tool_call: dict) -> str:
    """提取简要操作明细用于审计日志"""
    try:
        if tool == "exec":
            return str(tool_call.get("command", ""))[:200]
        if tool in ("read_file", "write_file", "list_dir", "edit"):
            return str(tool_call.get("path", ""))[:200]
        if tool in ("http_get", "http_post", "browse", "screenshot"):
            return str(tool_call.get("url", ""))[:200]
        if tool in ("search", "web_search"):
            return str(tool_call.get("query", ""))[:200]
        if tool in ("generate_pdf", "script_create"):
            return str(tool_call.get("content", tool_call.get("code", "")))[:100]
        if tool == "script_execute":
            script_id = tool_call.get("script_id")
            return f"script_id={script_id}" if script_id else str(tool_call.get("code", ""))[:100]
        return str(tool_call)[:200]
    except Exception:
        return ""


def execute_tool_call(tool_call: dict, user_id: int) -> str:
    """执行工具调用，返回结果字符串（所有路径/脚本/文件操作均按 user_id 隔离）"""
    tool = tool_call.get("tool")

    if tool == "generate_pdf":
        result = _tool_generate_pdf(tool_call.get("content", ""), user_id)
    elif tool == "exec":
        result = exec_cmd(tool_call.get("command", ""))
    elif tool == "read_file":
        result = read_file(tool_call.get("path", ""), user_id)
    elif tool == "write_file":
        result = write_file(tool_call.get("path", ""), tool_call.get("content", ""), user_id)
    elif tool == "list_dir":
        result = list_dir(tool_call.get("path", "."), user_id)
    elif tool == "edit":
        result = edit_file(tool_call.get("path", ""), tool_call.get("old_text", ""),
                           tool_call.get("new_text", ""), user_id)
    elif tool == "apply_patch":
        result = apply_patch(tool_call.get("patches", []), user_id)
    elif tool == "http_get":
        result = http_get(tool_call.get("url", ""), tool_call.get("headers"))
    elif tool == "http_post":
        result = http_post(tool_call.get("url", ""), tool_call.get("headers"), tool_call.get("data"))
    elif tool == "browse":
        result = browse(tool_call.get("url", ""), int(tool_call.get("timeout", 30)))
    elif tool == "screenshot":
        result = screenshot(tool_call.get("url", ""), int(tool_call.get("timeout", 30)), user_id)
    elif tool in ("search", "web_search"):
        result = web_search(tool_call.get("query", ""), int(tool_call.get("num", 5)))
    elif tool == "script_create":
        result = _tool_script_create(tool_call.get("code", ""), user_id)
    elif tool == "script_execute":
        result = _tool_script_execute(tool_call.get("script_id"), tool_call.get("code", ""), user_id)
    elif tool == "script_list":
        result = _tool_script_list(user_id)
    else:
        result = f"❌ 未知工具: {tool}"

    success = not result.startswith("❌")
    log_operation(user_id, f"tool:{tool}", detail=_op_detail(tool, tool_call),
                  success=success, error=result[:300] if not success else "")
    return result
