import os
import subprocess
import asyncio
import json
import httpx
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

from memory import MemoryManager
from cron import CronTaskManager, CronScheduler, CronParser, TaskExecutor
from script_manager import script_manager

memory_manager = MemoryManager()

from rag.knowledge_base import KnowledgeBase
knowledge_base = KnowledgeBase()

cron_task_manager = CronTaskManager()
cron_executor = TaskExecutor(cron_task_manager)
cron_scheduler = CronScheduler(cron_task_manager, cron_executor.execute)

# 依赖安装状态管理
installation_state = {
    'in_progress': False,
    'package': '',
    'progress': 0,
    'output': '',
    'success': False
}

# 文件存储配置
LOBSTER_CLAW_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'lobster-claw-files')
os.makedirs(LOBSTER_CLAW_FILES_DIR, exist_ok=True)

# 允许的文件扩展名（安全白名单）
ALLOWED_FILE_EXTENSIONS = {'.pdf', '.txt', '.csv', '.json', '.xlsx', '.xls', '.docx', '.doc', '.md', '.html', '.zip', '.rar', '.jpg', '.jpeg', '.png', '.gif'}

router = APIRouter(prefix="/api/lobster-claw")

claw_history = []
MAX_HISTORY = 100

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

ALLOWED_COMMANDS = [
    "echo", "dir", "ls", "type", "cat", "find", "grep",
    "date", "time", "whoami", "hostname", "ver", "uname",
    "ping", "tracert", "nslookup", "ipconfig", "ifconfig",
    "netstat", "tasklist", "ps", "tree", "cd", "pwd",
    "cls", "clear", "sort", "more", "less", "head", "tail",
    "wc", "uniq", "sort", "cut", "paste", "split", "join"
]

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ALLOWED_PATHS = [
    str(BASE_DIR),
    str(BASE_DIR / "web"),
    str(BASE_DIR / "data"),
    str(BASE_DIR / "skills"),
    str(BASE_DIR / "llm"),
    str(BASE_DIR / "config")
]

PERMISSION_LEVELS = {
    "admin": ["read_file", "write_file", "list_dir", "edit", "apply_patch",
              "exec", "http_get", "http_post", "browse", "screenshot",
              "web_search", "cron_add", "cron_delete", "cron_toggle",
              "agent_create", "agent_delete", "agent_update", "agent_add_memory",
              "agent_delete_memory", "search_memory"],
    "user": ["read_file", "list_dir", "exec", "http_get", "web_search",
             "browse", "screenshot", "agent_list", "agent_info",
             "agent_memory", "search_memory"],
    "guest": ["read_file", "list_dir", "web_search"]
}

operation_logs = []
MAX_LOGS = 1000

request_counts = {}
RATE_LIMIT = 100
RATE_LIMIT_WINDOW = 60

class ExecCommandRequest(BaseModel):
    command: str
    timeout: int = 30

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

class DirListRequest(BaseModel):
    path: str = "."

class HttpRequest(BaseModel):
    url: str
    headers: Optional[Dict[str, str]] = None
    data: Optional[Dict[str, Any]] = None

class BrowseRequest(BaseModel):
    url: str
    timeout: int = 30

class EditFileRequest(BaseModel):
    path: str
    old_text: str
    new_text: str

class ApplyPatchRequest(BaseModel):
    patches: List[Dict[str, Any]]

class WebSearchRequest(BaseModel):
    query: str
    count: int = 5

class CronRequest(BaseModel):
    name: str
    task_type: str
    content: str
    schedule: Optional[str] = None
    run_at: Optional[str] = None
    enabled: bool = True
    timeout: int = 300

class CronListRequest(BaseModel):
    pass

def is_command_safe(command: str) -> bool:
    cmd_lower = command.lower().strip()
    for dangerous in DANGEROUS_COMMANDS:
        if cmd_lower.startswith(dangerous) or dangerous in cmd_lower.split():
            return False
    return True

def sanitize_path(path: str) -> str:
    path = path.replace("..", "").replace("/", "\\").strip()
    if not path.startswith(str(BASE_DIR)):
        return os.path.join(BASE_DIR, path)
    return path

def is_path_allowed(path: str) -> bool:
    path = os.path.abspath(path)
    for allowed in ALLOWED_PATHS:
        if path.startswith(allowed):
            return True
    return False

def check_permission(permission: str, level: str = "admin") -> bool:
    return permission in PERMISSION_LEVELS.get(level, [])

def log_operation(operation: str, user: str = "unknown", ip: str = "unknown", success: bool = True, error: str = ""):
    log = {
        "id": len(operation_logs) + 1,
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "user": user,
        "ip": ip,
        "success": success,
        "error": error
    }
    operation_logs.insert(0, log)
    if len(operation_logs) > MAX_LOGS:
        operation_logs.pop()

def check_rate_limit(ip: str) -> bool:
    now = datetime.now().timestamp()
    if ip not in request_counts:
        request_counts[ip] = []
    request_counts[ip] = [t for t in request_counts[ip] if now - t < RATE_LIMIT_WINDOW]
    request_counts[ip].append(now)
    return len(request_counts[ip]) <= RATE_LIMIT

async def execute_shell_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )
        
        return {
            "success": True,
            "stdout": stdout.decode('utf-8', errors='replace'),
            "stderr": stderr.decode('utf-8', errors='replace'),
            "return_code": proc.returncode
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": f"命令执行超时（{timeout}秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def add_to_history(command: str, result: Dict[str, Any]):
    record = {
        "id": len(claw_history) + 1,
        "timestamp": datetime.now().isoformat(),
        "command": command,
        "result": result
    }
    claw_history.insert(0, record)
    if len(claw_history) > MAX_HISTORY:
        claw_history.pop()

@router.post("/exec")
async def exec_command(request: ExecCommandRequest):
    if not request.command.strip():
        log_operation("exec", success=False, error="命令不能为空")
        raise HTTPException(status_code=400, detail="命令不能为空")
    
    if not is_command_safe(request.command):
        result = {"success": False, "error": "安全警告：该命令不在白名单中，禁止执行"}
        add_to_history(request.command, result)
        log_operation(f"exec {request.command}", success=False, error="命令不在白名单")
        return result
    
    result = await execute_shell_command(request.command, request.timeout)
    add_to_history(request.command, result)
    log_operation(f"exec {request.command}", success=result["success"], error=result.get("error", ""))
    return result

@router.post("/read_file")
async def read_file(request: FileReadRequest):
    try:
        path = sanitize_path(request.path)
        if not is_path_allowed(path):
            result = {"success": False, "error": f"安全警告：访问路径不在允许范围内: {path}"}
            add_to_history(f"read_file {request.path}", result)
            log_operation(f"read_file {request.path}", success=False, error="路径不在允许范围")
            return result
        
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        result = {"success": True, "content": content, "path": path}
        add_to_history(f"read_file {request.path}", result)
        log_operation(f"read_file {request.path}", success=True)
        return result
    except HTTPException:
        raise
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"read_file {request.path}", result)
        log_operation(f"read_file {request.path}", success=False, error=str(e))
        return result

@router.post("/write_file")
async def write_file(request: FileWriteRequest):
    try:
        path = sanitize_path(request.path)
        if not is_path_allowed(path):
            result = {"success": False, "error": f"安全警告：写入路径不在允许范围内: {path}"}
            add_to_history(f"write_file {request.path}", result)
            log_operation(f"write_file {request.path}", success=False, error="路径不在允许范围")
            return result
        
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        result = {"success": True, "message": f"文件写入成功: {path}", "path": path}
        add_to_history(f"write_file {request.path}", result)
        log_operation(f"write_file {request.path}", success=True)
        return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"write_file {request.path}", result)
        return result

@router.post("/list_dir")
async def list_dir(request: DirListRequest = None):
    try:
        path = request.path if request else "."
        full_path = sanitize_path(path)
        
        if not os.path.isdir(full_path):
            raise HTTPException(status_code=404, detail="目录不存在")
        
        items = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            items.append({
                "name": item,
                "path": item_path,
                "type": "dir" if os.path.isdir(item_path) else "file",
                "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                "modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat()
            })
        
        result = {"success": True, "items": items, "path": full_path}
        add_to_history(f"list_dir {path}", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"list_dir {path}", result)
        return result

@router.post("/http_get")
async def http_get(request: HttpRequest):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                request.url,
                headers=request.headers or {}
            )
            
            result = {
                "success": True,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text[:10000] if len(response.text) > 10000 else response.text
            }
            add_to_history(f"http_get {request.url}", result)
            return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"http_get {request.url}", result)
        return result

@router.post("/http_post")
async def http_post(request: HttpRequest):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                request.url,
                headers=request.headers or {},
                json=request.data or {}
            )
            
            result = {
                "success": True,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text[:10000] if len(response.text) > 10000 else response.text
            }
            add_to_history(f"http_post {request.url}", result)
            return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"http_post {request.url}", result)
        return result

@router.post("/browse")
async def browse(request: BrowseRequest):
    try:
        async with httpx.AsyncClient(timeout=request.timeout) as client:
            response = await client.get(request.url)
            
            import re
            title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
            title = title_match.group(1) if title_match else "无标题"
            
            result = {
                "success": True,
                "url": request.url,
                "title": title,
                "status_code": response.status_code,
                "content_length": len(response.text)
            }
            add_to_history(f"browse {request.url}", result)
            return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"browse {request.url}", result)
        return result

@router.post("/screenshot")
async def screenshot(request: BrowseRequest):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        import base64
        
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--window-size=1920,1080')
        
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            driver.set_page_load_timeout(request.timeout)
            driver.get(request.url)
            
            screenshot_bytes = driver.get_screenshot_as_png()
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            result = {
                "success": True,
                "url": request.url,
                "screenshot": f"data:image/png;base64,{screenshot_base64}",
                "width": 1920,
                "height": 1080
            }
            add_to_history(f"screenshot {request.url}", result)
            return result
        finally:
            driver.quit()
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"screenshot {request.url}", result)
        return result

@router.post("/edit")
async def edit_file(request: EditFileRequest):
    try:
        path = sanitize_path(request.path)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if request.old_text not in content:
            return {"success": False, "error": "未找到要替换的文本"}
        
        new_content = content.replace(request.old_text, request.new_text)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        result = {"success": True, "message": f"文件编辑成功: {path}", "changes": 1}
        add_to_history(f"edit {request.path}", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"edit {request.path}", result)
        return result

@router.post("/apply_patch")
async def apply_patch(request: ApplyPatchRequest):
    try:
        changes_made = 0
        errors = []
        
        for patch in request.patches:
            path = sanitize_path(patch.get("path", ""))
            old_text = patch.get("old_text", "")
            new_text = patch.get("new_text", "")
            
            if not path or not old_text:
                errors.append(f"补丁参数不完整: {path}")
                continue
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if old_text in content:
                    new_content = content.replace(old_text, new_text)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    changes_made += 1
                else:
                    errors.append(f"未找到匹配文本: {path}")
            except Exception as e:
                errors.append(f"处理 {path} 失败: {str(e)}")
        
        result = {
            "success": len(errors) == 0,
            "message": f"补丁应用完成，成功 {changes_made} 个文件",
            "changes_made": changes_made,
            "errors": errors
        }
        add_to_history("apply_patch", result)
        return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history("apply_patch", result)
        return result

@router.post("/web_search")
async def web_search(request: WebSearchRequest):
    try:
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            results = []
            for result in ddgs.text(request.query, max_results=request.count):
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "description": result.get("body", "")
                })
        
        result = {"success": True, "query": request.query, "results": results, "count": len(results)}
        add_to_history(f"web_search {request.query}", result)
        return result
    except ImportError:
        result = {"success": False, "error": "未安装 duckduckgo_search，请安装: pip install duckduckgo-search"}
        add_to_history(f"web_search {request.query}", result)
        return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"web_search {request.query}", result)
        return result

agents = []

class AgentCreateRequest(BaseModel):
    name: str
    personality: Optional[str] = "default"
    permissions: Optional[List[str]] = None
    memory_size: int = 100

@router.post("/cron/add")
async def cron_add(request: CronRequest):
    try:
        if request.task_type not in ['ai', 'command']:
            return {"success": False, "error": "任务类型必须是 'ai' 或 'command'"}
        
        if not request.schedule and not request.run_at:
            return {"success": False, "error": "必须指定 schedule（cron表达式）或 run_at（执行时间）"}
        
        if request.schedule:
            try:
                CronParser.parse(request.schedule)
            except ValueError as e:
                return {"success": False, "error": f"Cron表达式格式错误: {e}"}
        
        if request.task_type == 'command' and not is_command_safe(request.content):
            return {"success": False, "error": "安全警告：该命令不在白名单中"}
        
        task_id = cron_task_manager.add_task(
            name=request.name,
            task_type=request.task_type,
            content=request.content,
            schedule=request.schedule,
            run_at=request.run_at,
            enabled=request.enabled,
            timeout=request.timeout
        )
        
        task = cron_task_manager.get_task(task_id)
        
        if request.schedule and task['enabled']:
            next_run = CronParser.get_next_run(request.schedule)
            cron_task_manager.update_task(task_id, next_run_at=next_run.isoformat())
        
        result = {"success": True, "message": "定时任务创建成功", "task": task}
        add_to_history(f"cron_add {request.name}", result)
        return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"cron_add {request.name}", result)
        return result

@router.get("/cron/list")
async def cron_list(enabled: Optional[bool] = None):
    tasks = cron_task_manager.list_tasks(enabled=enabled)
    result = {"success": True, "tasks": tasks}
    return result

@router.get("/cron/{task_id}")
async def cron_get(task_id: int):
    task = cron_task_manager.get_task(task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    return {"success": True, "task": task}

@router.put("/cron/{task_id}")
async def cron_update(task_id: int, request: CronRequest):
    try:
        task = cron_task_manager.get_task(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        
        if request.task_type not in ['ai', 'command']:
            return {"success": False, "error": "任务类型必须是 'ai' 或 'command'"}
        
        if request.schedule:
            try:
                CronParser.parse(request.schedule)
            except ValueError as e:
                return {"success": False, "error": f"Cron表达式格式错误: {e}"}
        
        if request.task_type == 'command' and not is_command_safe(request.content):
            return {"success": False, "error": "安全警告：该命令不在白名单中"}
        
        updates = {
            'name': request.name,
            'task_type': request.task_type,
            'content': request.content,
            'schedule': request.schedule,
            'run_at': request.run_at,
            'enabled': 1 if request.enabled else 0,
            'timeout': request.timeout
        }
        
        cron_task_manager.update_task(task_id, **updates)
        
        if request.schedule and request.enabled:
            next_run = CronParser.get_next_run(request.schedule)
            cron_task_manager.update_task(task_id, next_run_at=next_run.isoformat())
        
        task = cron_task_manager.get_task(task_id)
        result = {"success": True, "message": "任务已更新", "task": task}
        add_to_history(f"cron_update {task_id}", result)
        return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"cron_update {task_id}", result)
        return result

@router.delete("/cron/{task_id}")
async def cron_delete(task_id: int):
    task = cron_task_manager.get_task(task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    
    cron_task_manager.delete_task(task_id)
    result = {"success": True, "message": f"任务已删除: {task['name']}"}
    add_to_history(f"cron_delete {task_id}", result)
    return result

@router.post("/cron/toggle/{task_id}")
async def cron_toggle(task_id: int):
    task = cron_task_manager.toggle_task(task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    
    if task['enabled'] and task['schedule']:
        next_run = CronParser.get_next_run(task['schedule'])
        cron_task_manager.update_task(task_id, next_run_at=next_run.isoformat())
    
    result = {"success": True, "message": f"任务状态已更新: {'启用' if task['enabled'] else '禁用'}", "task": task}
    add_to_history(f"cron_toggle {task_id}", result)
    return result

@router.get("/cron/{task_id}/runs")
async def cron_runs(task_id: int, limit: int = 50):
    task = cron_task_manager.get_task(task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    
    runs = cron_task_manager.get_runs(task_id, limit=limit)
    return {"success": True, "runs": runs}

@router.post("/cron/{task_id}/run-now")
async def cron_run_now(task_id: int):
    task = cron_task_manager.get_task(task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    
    if not task['enabled']:
        return {"success": False, "error": "任务已禁用"}
    
    cron_scheduler.run_now(task_id)
    result = {"success": True, "message": "任务已触发执行"}
    add_to_history(f"cron_run_now {task_id}", result)
    return result

@router.get("/history")
async def get_history():
    return {"success": True, "history": claw_history}

@router.delete("/history/{record_id}")
async def delete_history(record_id: int):
    global claw_history
    claw_history = [r for r in claw_history if r["id"] != record_id]
    return {"success": True, "message": "记录已删除"}

@router.delete("/history")
async def clear_history():
    global claw_history
    claw_history = []
    return {"success": True, "message": "历史记录已清空"}

@router.post("/agent/create")
async def agent_create(request: AgentCreateRequest):
    try:
        agent_id = len(agents) + 1
        default_permissions = ["read_file", "list_dir", "exec", "http_get"]
        
        agent = {
            "id": agent_id,
            "name": request.name,
            "personality": request.personality,
            "permissions": request.permissions or default_permissions,
            "memory_size": request.memory_size,
            "memory": [],
            "created_at": datetime.now().isoformat(),
            "last_used": None
        }
        agents.append(agent)
        
        result = {"success": True, "message": f"Agent创建成功", "agent": agent}
        add_to_history(f"agent_create {request.name}", result)
        return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"agent_create {request.name}", result)
        return result

@router.get("/agent/list")
async def agent_list():
    result = {"success": True, "agents": agents}
    return result

@router.get("/agent/{agent_id}")
async def agent_get(agent_id: int):
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "agent": agent}

@router.put("/agent/{agent_id}")
async def agent_update(agent_id: int, request: AgentCreateRequest):
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    
    agent["name"] = request.name
    agent["personality"] = request.personality
    agent["permissions"] = request.permissions or agent["permissions"]
    agent["memory_size"] = request.memory_size
    
    result = {"success": True, "message": f"Agent更新成功", "agent": agent}
    add_to_history(f"agent_update {agent_id}", result)
    return result

@router.delete("/agent/{agent_id}")
async def agent_delete(agent_id: int):
    global agents
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    
    agents = [a for a in agents if a["id"] != agent_id]
    result = {"success": True, "message": f"Agent已删除: {agent['name']}"}
    add_to_history(f"agent_delete {agent_id}", result)
    return result

@router.post("/agent/{agent_id}/add_memory")
async def agent_add_memory(agent_id: int, request: Dict[str, Any]):
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    
    memory_item = {
        "id": len(agent["memory"]) + 1,
        "content": request.get("content", ""),
        "timestamp": datetime.now().isoformat(),
        "type": request.get("type", "short_term")
    }
    agent["memory"].append(memory_item)
    
    if len(agent["memory"]) > agent["memory_size"]:
        agent["memory"].pop(0)
    
    result = {"success": True, "message": "记忆已添加"}
    add_to_history(f"agent_add_memory {agent_id}", result)
    return result

@router.get("/agent/{agent_id}/memory")
async def agent_get_memory(agent_id: int):
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    return {"success": True, "memory": agent["memory"]}

@router.delete("/agent/{agent_id}/memory/{memory_id}")
async def agent_delete_memory(agent_id: int, memory_id: int):
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return {"success": False, "error": "Agent不存在"}
    
    agent["memory"] = [m for m in agent["memory"] if m["id"] != memory_id]
    result = {"success": True, "message": "记忆已删除"}
    add_to_history(f"agent_delete_memory {agent_id}", result)
    return result

@router.post("/search_memory")
async def search_memory(request: Dict[str, Any]):
    try:
        query = request.get("query", "")
        agent_id = request.get("agent_id", None)
        max_results = request.get("max_results", 10)
        
        search_pool = []
        if agent_id:
            agent = next((a for a in agents if a["id"] == agent_id), None)
            if agent:
                search_pool = agent["memory"]
        else:
            for agent in agents:
                search_pool.extend(agent["memory"])
        
        search_pool.extend(claw_history)
        
        results = []
        for item in search_pool:
            content = ""
            if isinstance(item, dict):
                if "content" in item:
                    content = item["content"]
                elif "command" in item:
                    content = item["command"]
                    if item.get("result"):
                        content += str(item["result"])
            
            if query.lower() in content.lower():
                results.append({
                    "content": content,
                    "timestamp": item.get("timestamp", ""),
                    "type": item.get("type", "unknown")
                })
        
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        
        result = {
            "success": True,
            "query": query,
            "results": results[:max_results],
            "count": len(results)
        }
        add_to_history(f"search_memory {query}", result)
        return result
    except Exception as e:
        result = {"success": False, "error": str(e)}
        add_to_history(f"search_memory {query}", result)
        return result

@router.get("/security/logs")
async def get_security_logs(limit: int = 50):
    return {"success": True, "logs": operation_logs[:limit]}

@router.get("/security/stats")
async def get_security_stats():
    success_count = sum(1 for log in operation_logs if log["success"])
    error_count = len(operation_logs) - success_count
    
    operation_counts = {}
    for log in operation_logs:
        op = log["operation"].split()[0] if " " in log["operation"] else log["operation"]
        operation_counts[op] = operation_counts.get(op, 0) + 1
    
    result = {
        "success": True,
        "total_operations": len(operation_logs),
        "success_rate": f"{(success_count / len(operation_logs) * 100):.2f}%" if operation_logs else "0%",
        "success_count": success_count,
        "error_count": error_count,
        "operation_counts": operation_counts,
        "active_agents": len(agents),
        "active_cron_tasks": sum(1 for t in cron_tasks if t["enabled"]),
        "memory_items": sum(len(a["memory"]) for a in agents),
        "history_count": len(claw_history)
    }
    return result

@router.get("/security/allowed_paths")
async def get_allowed_paths():
    return {"success": True, "paths": ALLOWED_PATHS}

@router.get("/security/permission_levels")
async def get_permission_levels():
    return {"success": True, "levels": PERMISSION_LEVELS}

SKILLS_DIR = BASE_DIR / "skills"

class SkillExecuteRequest(BaseModel):
    skill_name: str
    parameters: Optional[Dict[str, Any]] = None

def load_skill(skill_name: str) -> Optional[Dict[str, Any]]:
    skill_path = SKILLS_DIR / f"{skill_name}.md"
    if not skill_path.exists():
        return None
    
    try:
        with open(skill_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        skill = {
            "name": skill_name,
            "path": str(skill_path),
            "content": content
        }
        
        lines = content.split('\n')
        for line in lines:
            if line.startswith("# "):
                skill["title"] = line[2:].strip()
            elif line.startswith("## Description"):
                skill["description"] = ""
            elif line.startswith("##"):
                break
            elif "description" in skill:
                skill["description"] += line + "\n"
        
        return skill
    except Exception as e:
        return None

def discover_skills() -> List[Dict[str, Any]]:
    skills = []
    if SKILLS_DIR.exists():
        for md_file in SKILLS_DIR.glob("*.md"):
            skill_name = md_file.stem
            skill = load_skill(skill_name)
            if skill:
                skills.append(skill)
    return skills

@router.get("/skills/discover")
async def discover_skills_api():
    skills = discover_skills()
    result = {"success": True, "skills": skills, "count": len(skills)}
    add_to_history("skills_discover", result)
    return result

@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str):
    skill = load_skill(skill_name)
    if not skill:
        return {"success": False, "error": f"技能不存在: {skill_name}"}
    return {"success": True, "skill": skill}

@router.post("/skills/execute")
async def execute_skill(request: SkillExecuteRequest):
    try:
        skill = load_skill(request.skill_name)
        if not skill:
            return {"success": False, "error": f"技能不存在: {request.skill_name}"}
        
        from skills.skill_manager import get_skill_configs
        
        configs = get_skill_configs()
        skill_config = next((c for c in configs if c.name.lower() == request.skill_name.lower()), None)
        
        if skill_config:
            from skills.base import BaseSkill
            skill_instance = BaseSkill.from_config(skill_config)
            result = await skill_instance.execute(request.parameters or {})
            
            execution_result = {
                "success": True,
                "skill": request.skill_name,
                "title": skill.get("title", request.skill_name),
                "description": skill.get("description", ""),
                "result": result,
                "type": "configured_skill"
            }
            add_to_history(f"skills_execute {request.skill_name}", execution_result)
            return execution_result
        else:
            execution_result = {
                "success": True,
                "skill": request.skill_name,
                "title": skill.get("title", request.skill_name),
                "description": skill.get("description", ""),
                "message": "技能已加载，但未在系统中配置执行器",
                "type": "discovered_skill"
            }
            add_to_history(f"skills_execute {request.skill_name}", execution_result)
            return execution_result
    except Exception as e:
        result = {"success": False, "error": str(e), "skill": request.skill_name}
        add_to_history(f"skills_execute {request.skill_name}", result)
        return result

chat_sessions = {}
MAX_CHAT_HISTORY = 50

class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatStreamRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model_name: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None

def get_default_llm_adapter(model_name: Optional[str] = None):
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
        return None

def get_image_models():
    try:
        from models.model_manager import ModelManager
        model_manager = ModelManager()
        return [m for m in model_manager.get_all() if m.api_key and m.enabled and m.model_type == "image"]
    except Exception as e:
        return []

def get_video_models():
    try:
        from models.model_manager import ModelManager
        model_manager = ModelManager()
        return [m for m in model_manager.get_all() if m.api_key and m.enabled and m.model_type == "video"]
    except Exception as e:
        return []


@router.get("/chat/models")
async def get_chat_models():
    try:
        from models.model_manager import ModelManager
        model_manager = ModelManager()
        configured_models = [m for m in model_manager.get_all() if m.api_key and m.enabled and m.model_type == "text"]
        return {
            "success": True,
            "models": [{"name": m.model_name, "provider": m.api_type, "model_id": m.name} for m in configured_models]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def detect_generation_type(message: str) -> str:
    message_lower = message.lower()
    video_keywords = ["生成视频", "视频生成", "画视频", "制作视频", "视频制作", "视频内容"]
    image_keywords = ["画图", "画画", "绘图", "绘制", "生成图片", "图片生成", "生成图像", "图像生成", "生成图", "画一张", "画个"]
    
    for keyword in video_keywords:
        if keyword in message_lower:
            return "video"
    
    for keyword in image_keywords:
        if keyword in message_lower:
            return "image"
    
    return "text"

def get_or_create_session(session_id: Optional[str] = None) -> str:
    if session_id and session_id in chat_sessions:
        return session_id
    
    new_session_id = f"claw_session_{len(chat_sessions) + 1}_{datetime.now().timestamp()}"
    chat_sessions[new_session_id] = {
        "id": new_session_id,
        "messages": [],
        "created_at": datetime.now().isoformat(),
        "last_used": datetime.now().isoformat()
    }
    return new_session_id

async def generate_chat_response(session_id: str, message: str, model_name: Optional[str] = None):
    adapter = get_default_llm_adapter()
    if not adapter:
        return {"success": False, "error": "未找到可用的LLM适配器"}
    
    session = chat_sessions.get(session_id)
    if not session:
        session_id = get_or_create_session()
        session = chat_sessions[session_id]
    
    system_prompt = """你是龙虾Claw，一个强大的AI智能体助手。你可以执行以下操作：
1. 回答用户问题
2. 执行Shell命令（dir, ls, echo等）
3. 读取/写入/编辑文件
4. 搜索网页
5. 执行定时任务
6. 管理智能体

请根据用户的需求，选择合适的工具执行。如果需要执行工具，请使用<tool>标签包裹工具调用。"""
    
    context = session["messages"][-10:]
    messages = adapter.create_prompt(system_prompt, message, context)
    
    try:
        response = adapter.chat(messages)
        return {"success": True, "content": response.content, "session_id": session_id}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/chat/message")
async def chat_message(request: ChatMessageRequest):
    session_id = get_or_create_session(request.session_id)
    result = await generate_chat_response(session_id, request.message)
    
    if result["success"]:
        session = chat_sessions[session_id]
        session["messages"].append({"role": "user", "content": request.message, "timestamp": datetime.now().isoformat()})
        session["messages"].append({"role": "assistant", "content": result["content"], "timestamp": datetime.now().isoformat()})
        session["last_used"] = datetime.now().isoformat()
        
        if len(session["messages"]) > MAX_CHAT_HISTORY:
            session["messages"] = session["messages"][-MAX_CHAT_HISTORY:]
    
    add_to_history(f"chat {request.message[:50]}", result)
    return result

# 存储上传的文件信息
uploaded_files = {}

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """上传文件到服务器"""
    results = []
    upload_dir = BASE_DIR / "web" / "static" / "uploads" / "claw"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    for file in files:
        try:
            # 生成唯一文件名
            file_ext = Path(file.filename).suffix
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_name = f"{timestamp}_{os.urandom(8).hex()}{file_ext}"
            file_path = upload_dir / unique_name
            
            # 保存文件
            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # 提取文本内容
            text_content = ""
            try:
                if file_ext.lower() in ['.txt', '.md', '.json', '.py', '.js', '.html', '.css', '.xml', '.csv']:
                    text_content = content.decode('utf-8')
                elif file_ext.lower() in ['.doc', '.docx']:
                    try:
                        from docx import Document
                        doc = Document(file_path)
                        text_content = '\n'.join([para.text for para in doc.paragraphs])
                    except ImportError:
                        text_content = f"[需要安装 python-docx 库来解析Word文档]"
                    except Exception as e:
                        text_content = f"[解析Word文档失败: {str(e)}]"
                elif file_ext.lower() == '.pdf':
                    try:
                        import fitz
                        doc = fitz.open(file_path)
                        text_content = '\n'.join([page.get_text() for page in doc])
                    except ImportError:
                        text_content = f"[需要安装 PyMuPDF(fitz) 库来解析PDF文档]"
                    except Exception as e:
                        text_content = f"[解析PDF文档失败: {str(e)}]"
                elif file_ext.lower() in ['.xls', '.xlsx']:
                    try:
                        import pandas as pd
                        df = pd.read_excel(file_path)
                        text_content = df.to_string()
                    except ImportError:
                        text_content = f"[需要安装 pandas 和 openpyxl 库来解析Excel文件]"
                    except Exception as e:
                        text_content = f"[解析Excel文件失败: {str(e)}]"
                elif file_ext.lower() in ['.ppt', '.pptx']:
                    try:
                        from pptx import Presentation
                        prs = Presentation(file_path)
                        text_content = ''
                        for slide in prs.slides:
                            for shape in slide.shapes:
                                if hasattr(shape, 'text'):
                                    text_content += shape.text + '\n'
                    except ImportError:
                        text_content = f"[需要安装 python-pptx 库来解析PowerPoint文件]"
                    except Exception as e:
                        text_content = f"[解析PowerPoint文件失败: {str(e)}]"
                else:
                    text_content = f"[不支持的文件类型 {file_ext}]"
            except Exception as e:
                text_content = f"[提取文件内容失败: {str(e)}]"
            
            file_id = os.urandom(16).hex()
            uploaded_files[file_id] = {
                'id': file_id,
                'filename': file.filename,
                'path': str(file_path),
                'content': text_content,
                'size': len(content),
                'timestamp': datetime.now().isoformat()
            }
            
            results.append({
                'success': True,
                'id': file_id,
                'filename': file.filename,
                'size': len(content),
                'content_preview': text_content[:200] if text_content else ""
            })
        except Exception as e:
            results.append({
                'success': False,
                'filename': file.filename,
                'error': str(e)
            })
    
    return {'results': results}

@router.post("/upload/text")
async def upload_text_file(file: UploadFile = File(...)):
    """上传文件并返回解析后的文本内容"""
    try:
        content = await file.read()
        file_ext = Path(file.filename).suffix.lower()
        upload_dir = BASE_DIR / "web" / "static" / "uploads" / "claw"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"[DEBUG] 上传文件: {file.filename}, 大小: {len(content)} bytes, 扩展名: {file_ext}")
        
        # 保存文件到上传目录（持久化）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"{timestamp}_{os.urandom(4).hex()}{file_ext}"
        file_path = upload_dir / safe_filename
        with open(file_path, 'wb') as f:
            f.write(content)
        
        print(f"[DEBUG] 文件已保存到: {file_path}")
        
        # 根据文件类型解析内容
        text_content = ""
        try:
            print(f"[DEBUG] 文件类型判断: file_ext={file_ext}")
            if file_ext in ['.txt', '.md', '.json', '.py', '.js', '.html', '.css', '.xml', '.csv']:
                text_content = content.decode('utf-8')
                print(f"[DEBUG] 文本文件解析完成，长度: {len(text_content)}")
            elif file_ext in ['.doc', '.docx']:
                try:
                    from docx import Document
                    doc = Document(file_path)
                    text_content = '\n'.join([para.text for para in doc.paragraphs])
                except ImportError:
                    text_content = f"[需要安装 python-docx 库来解析Word文档]"
                except Exception as e:
                    text_content = f"[解析Word文档失败: {str(e)}]"
            elif file_ext == '.pdf':
                print(f"[DEBUG] 进入PDF解析分支")
                try:
                    import fitz  # PyMuPDF（优先使用）
                    print(f"[DEBUG] fitz导入成功")
                    doc = fitz.open(file_path)
                    text_content = '\n'.join([page.get_text() for page in doc])
                    print(f"[DEBUG] PyMuPDF提取文本长度: {len(text_content)}")
                    
                    # 如果提取的文本很少，可能是扫描件PDF，尝试OCR
                    if len(text_content.strip()) < 100:
                        print("[DEBUG] 文本内容过少，尝试OCR识别...")
                        # 优先尝试pytesseract
                        try:
                            import pytesseract
                            from PIL import Image
                            
                            ocr_text = ""
                            for page in doc:
                                pix = page.get_pixmap()
                                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                ocr_text += pytesseract.image_to_string(img, lang='chi_sim') + '\n'
                            
                            text_content = ocr_text
                            print(f"[DEBUG] PyTesseract OCR识别文本长度: {len(text_content)}")
                        except ImportError:
                                print("[DEBUG] 未安装pytesseract，尝试PaddleOCR...")
                                # 备选方案：PaddleOCR 3.x
                                try:
                                    from paddleocr import PaddleOCR
                                    import numpy as np
                                    
                                    ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
                                    ocr_text = ""
                                    for page in doc:
                                        pix = page.get_pixmap()
                                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                        img_array = np.array(img)
                                        result = ocr.predict(img_array)
                                        if result and len(result) > 0:
                                            for item in result:
                                                if isinstance(item, dict) and 'text' in item:
                                                    ocr_text += item['text'] + '\n'
                                                elif isinstance(item, list) and len(item) > 1:
                                                    ocr_text += str(item[1]) + '\n'
                                    
                                    text_content = ocr_text
                                    print(f"[DEBUG] PaddleOCR识别文本长度: {len(text_content)}")
                                except ImportError as e:
                                    print(f"[DEBUG] 未安装PaddleOCR相关库: {str(e)}")
                                except Exception as e:
                                    print(f"[DEBUG] PaddleOCR识别失败: {str(e)}")
                        except Exception as e:
                            print(f"[DEBUG] PyTesseract OCR识别失败，尝试PaddleOCR...")
                            # pytesseract失败，尝试PaddleOCR 3.x
                            try:
                                from paddleocr import PaddleOCR
                                import numpy as np
                                
                                ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
                                ocr_text = ""
                                for page in doc:
                                    pix = page.get_pixmap()
                                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                    img_array = np.array(img)
                                    result = ocr.predict(img_array)
                                    if result and len(result) > 0:
                                        for item in result:
                                            if isinstance(item, dict) and 'text' in item:
                                                ocr_text += item['text'] + '\n'
                                            elif isinstance(item, list) and len(item) > 1:
                                                ocr_text += str(item[1]) + '\n'
                                
                                text_content = ocr_text
                                print(f"[DEBUG] PaddleOCR识别文本长度: {len(text_content)}")
                            except Exception as e:
                                print(f"[DEBUG] PaddleOCR也失败: {str(e)}")
                            
                except ImportError:
                    try:
                        from PyPDF2 import PdfReader
                        reader = PdfReader(file_path)
                        text_content = '\n'.join([page.extract_text() or '' for page in reader.pages])
                        print(f"[DEBUG] PyPDF2提取文本长度: {len(text_content)}")
                        
                        # 如果提取的文本很少，尝试OCR
                        if len(text_content.strip()) < 100:
                            print("[DEBUG] 文本内容过少，尝试OCR识别...")
                            try:
                                import pytesseract
                                from PIL import Image
                                import fitz
                                
                                doc = fitz.open(file_path)
                                ocr_text = ""
                                for page in doc:
                                    pix = page.get_pixmap()
                                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                    ocr_text += pytesseract.image_to_string(img, lang='chi_sim') + '\n'
                                
                                text_content = ocr_text
                                print(f"[DEBUG] PyTesseract OCR识别文本长度: {len(text_content)}")
                            except ImportError:
                                print("[DEBUG] 未安装pytesseract，尝试PaddleOCR...")
                                try:
                                    from paddleocr import PaddleOCR
                                    import fitz
                                    import numpy as np
                                    
                                    ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
                                    doc = fitz.open(file_path)
                                    ocr_text = ""
                                    for page in doc:
                                        pix = page.get_pixmap()
                                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                        img_array = np.array(img)
                                        result = ocr.predict(img_array)
                                        if result and len(result) > 0:
                                            for item in result:
                                                if isinstance(item, dict) and 'text' in item:
                                                    ocr_text += item['text'] + '\n'
                                                elif isinstance(item, list) and len(item) > 1:
                                                    ocr_text += str(item[1]) + '\n'
                                    
                                    text_content = ocr_text
                                    print(f"[DEBUG] PaddleOCR识别文本长度: {len(text_content)}")
                                except ImportError:
                                    print("[DEBUG] 未安装OCR相关库")
                                except Exception as e:
                                    print(f"[DEBUG] OCR识别失败: {str(e)}")
                            except Exception as e:
                                print(f"[DEBUG] OCR识别失败: {str(e)}")
                                
                    except ImportError:
                        text_content = f"[需要安装 PyMuPDF(fitz) 或 PyPDF2 库来解析PDF文档]"
                    except Exception as e:
                        text_content = f"[使用PyPDF2解析PDF失败: {str(e)}]"
                except Exception as e:
                    text_content = f"[解析PDF文档失败: {str(e)}]"
            elif file_ext in ['.xls', '.xlsx']:
                try:
                    import pandas as pd
                    df = pd.read_excel(file_path)
                    text_content = df.to_string()
                except ImportError:
                    text_content = f"[需要安装 pandas 和 openpyxl 库来解析Excel文件]"
                except Exception as e:
                    text_content = f"[解析Excel文件失败: {str(e)}]"
            elif file_ext in ['.ppt', '.pptx']:
                try:
                    from pptx import Presentation
                    prs = Presentation(file_path)
                    text_content = ''
                    for slide in prs.slides:
                        for shape in slide.shapes:
                            if hasattr(shape, 'text'):
                                text_content += shape.text + '\n'
                except ImportError:
                    text_content = f"[需要安装 python-pptx 库来解析PowerPoint文件]"
                except Exception as e:
                    text_content = f"[解析PowerPoint文件失败: {str(e)}]"
            else:
                text_content = f"[不支持的文件类型 {file_ext}]"
        except Exception as e:
            text_content = f"[解析文件失败: {str(e)}]"
        
        print(f"[DEBUG] 解析内容长度: {len(text_content)}")
        
        return {'success': True, 'filename': file.filename, 'content': text_content}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@router.post("/chat/stream")
async def chat_stream(request: ChatStreamRequest):
    session_id = get_or_create_session(request.session_id)
    session = chat_sessions[session_id]
    
    # 构建包含文件信息的消息内容
    full_message = request.message
    if request.files:
        print(f"[DEBUG] 收到 {len(request.files)} 个文件")
        file_info = []
        for i, file_item in enumerate(request.files):
            filename = file_item.get('filename', '')
            content = file_item.get('content', '')
            print(f"[DEBUG] 文件 {i+1}: {filename}, 内容长度: {len(content) if content else 0}")
            if filename:
                if content:
                    file_info.append(f"\n📄 文件: {filename}\n```\n{content}\n```")
                else:
                    file_info.append(f"\n📄 文件: {filename} (已上传但无法提取内容)")
        
        if file_info:
            full_message = request.message + "\n\n" + "".join(file_info)
    
    session["messages"].append({"role": "user", "content": full_message, "timestamp": datetime.now().isoformat()})
    session["last_used"] = datetime.now().isoformat()
    
    generation_type = detect_generation_type(request.message)
    
    if generation_type == "image":
        image_models = get_image_models()
        if not image_models:
            async def error_generator():
                yield f"data: {json.dumps({'success': False, 'error': '未配置文生图模型，请先在模型配置中添加文生图模型'})}\n\n"
            return StreamingResponse(error_generator(), media_type="text/event-stream")
        
        def image_generator():
            try:
                from engine.agent_worker import create_image_adapter
                
                yield f"data: {json.dumps({'success': True, 'content': '🎨 正在调用文生图模型生成图片...', 'session_id': session_id})}\n\n"
                
                model = image_models[0]
                adapter = create_image_adapter(model)
                
                prompt = request.message
                for keyword in ["画图", "画画", "绘图", "绘制", "生成图片", "图片生成", "生成图像", "图像生成", "生成图", "画一张", "画个"]:
                    prompt = prompt.replace(keyword, "").strip()
                
                response = adapter.generate(
                    prompt=prompt,
                    n=1,
                    size="1024x1024"
                )
                
                if response.success:
                    image_url = response.image_url
                    image_data = response.image_data.decode('utf-8') if response.image_data else None
                    
                    if image_url:
                        content = f"🖼️ 图片生成成功！\n\n![生成的图片]({image_url})"
                    elif image_data:
                        content = f"🖼️ 图片生成成功！\n\n![生成的图片](data:image/png;base64,{image_data})"
                    else:
                        content = f"🖼️ 图片生成成功，但无法获取图片数据"
                    
                    session["messages"].append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat()})
                    if len(session["messages"]) > MAX_CHAT_HISTORY:
                        session["messages"] = session["messages"][-MAX_CHAT_HISTORY:]
                    
                    yield f"data: {json.dumps({'success': True, 'content': content, 'session_id': session_id})}\n\n"
                else:
                    error_msg = f"❌ 图片生成失败: {response.error}"
                    session["messages"].append({"role": "assistant", "content": error_msg, "timestamp": datetime.now().isoformat()})
                    yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                
                yield f"data: {json.dumps({'success': True, 'content': '', 'session_id': session_id, 'done': True})}\n\n"
            except Exception as e:
                error_msg = f"❌ 图片生成异常: {str(e)}"
                session["messages"].append({"role": "assistant", "content": error_msg, "timestamp": datetime.now().isoformat()})
                yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
        
        return StreamingResponse(image_generator(), media_type="text/event-stream")
    
    elif generation_type == "video":
        video_models = get_video_models()
        if not video_models:
            async def error_generator():
                yield f"data: {json.dumps({'success': False, 'error': '未配置文生视频模型，请先在模型配置中添加文生视频模型'})}\n\n"
            return StreamingResponse(error_generator(), media_type="text/event-stream")
        
        def video_generator():
            try:
                from engine.agent_worker import create_video_adapter
                import time
                
                yield f"data: {json.dumps({'success': True, 'content': '🎬 正在调用文生视频模型生成视频...', 'session_id': session_id})}\n\n"
                
                model = video_models[0]
                adapter = create_video_adapter(model)
                
                prompt = request.message
                for keyword in ["生成视频", "视频生成", "画视频", "制作视频", "视频制作", "视频内容"]:
                    prompt = prompt.replace(keyword, "").strip()
                
                video_data = {
                    "model": model.model_name,
                    "prompt": prompt,
                    "width": 1024,
                    "height": 576,
                    "num_frames": 48,
                    "frame_rate": 8
                }
                
                response = adapter.generate(**video_data)
                
                if response.success and (hasattr(response, 'video_id') or hasattr(response, 'task_id')):
                    video_id = getattr(response, 'video_id', getattr(response, 'task_id', None))
                    yield f"data: {json.dumps({'success': True, 'content': f'⏳ 视频生成任务已创建，正在生成中...', 'session_id': session_id})}\n\n"
                    
                    max_wait_time = 300
                    start_time = time.time()
                    
                    while time.time() - start_time < max_wait_time:
                        task_info = adapter.get_status(video_id)
                        if task_info:
                            status = task_info.get("status", "unknown")
                            progress = task_info.get("progress", 0)
                            
                            if status == "completed" and task_info.get("video_url"):
                                content = f"🎬 视频生成成功！\n\n<video src=\"{task_info['video_url']}\" controls style=\"max-width: 100%; border-radius: 8px;\"></video>"
                                session["messages"].append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat()})
                                if len(session["messages"]) > MAX_CHAT_HISTORY:
                                    session["messages"] = session["messages"][-MAX_CHAT_HISTORY:]
                                
                                yield f"data: {json.dumps({'success': True, 'content': content, 'session_id': session_id})}\n\n"
                                break
                            elif status == "failed":
                                error_msg = f"❌ 视频生成失败: {task_info.get('error', '未知错误')}"
                                session["messages"].append({"role": "assistant", "content": error_msg, "timestamp": datetime.now().isoformat()})
                                yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                                break
                            else:
                                yield f"data: {json.dumps({'success': True, 'content': f'⏳ 视频生成中... {progress}%', 'session_id': session_id})}\n\n"
                        
                        time.sleep(3)
                    else:
                        error_msg = "❌ 视频生成超时，请稍后查询视频状态"
                        session["messages"].append({"role": "assistant", "content": error_msg, "timestamp": datetime.now().isoformat()})
                        yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                else:
                    error_msg = f"❌ 创建视频生成任务失败: {response.error}"
                    session["messages"].append({"role": "assistant", "content": error_msg, "timestamp": datetime.now().isoformat()})
                    yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                
                yield f"data: {json.dumps({'success': True, 'content': '', 'session_id': session_id, 'done': True})}\n\n"
            except Exception as e:
                error_msg = f"❌ 视频生成异常: {str(e)}"
                session["messages"].append({"role": "assistant", "content": error_msg, "timestamp": datetime.now().isoformat()})
                yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
        
        return StreamingResponse(video_generator(), media_type="text/event-stream")
    
    adapter = get_default_llm_adapter(request.model_name)
    if not adapter:
        async def error_generator():
            yield f"data: {json.dumps({'success': False, 'error': '未找到可用的LLM适配器'})}\n\n"
        return StreamingResponse(error_generator(), media_type="text/event-stream")
    
    # 根据是否有文件上传，使用不同的系统提示词
    if request.files:
        system_prompt = """你是龙虾Claw，一个强大的AI智能体助手。你可以帮助用户回答问题、分析信息、提供建议。当提供了工具执行结果时，请基于结果给出详细的解答和说明。

你拥有记忆能力，可以记住用户的偏好、重要事实和历史对话。以下是与当前问题相关的记忆信息，请参考这些信息来回答用户的问题。

重要规则：用户已上传文件，请直接分析文件内容并给出回答，不需要创建脚本。"""
    else:
        system_prompt = """你是龙虾Claw，一个强大的AI智能体助手。你可以帮助用户回答问题、分析信息、提供建议。当提供了工具执行结果时，请基于结果给出详细的解答和说明。

你拥有记忆能力，可以记住用户的偏好、重要事实和历史对话。以下是与当前问题相关的记忆信息，请参考这些信息来回答用户的问题。

你具备以下特殊能力：
- 生成中文PDF文档：当用户要求生成PDF时，你可以通过编写Python脚本来生成。系统已安装fpdf2库，并且会自动查找系统中文字体（微软雅黑等）来确保中文正确显示。生成的PDF文件会自动保存并提供下载链接。

重要规则：当你发现无法直接通过文字回答完成用户的任务时（例如需要计算、数据处理、文件操作、系统检查、生成PDF等），请在回复开头添加标记 [NEED_SCRIPT]，表示需要创建Python脚本来自动完成任务。系统会自动根据你的回复生成并执行脚本。"""
    
    # 当有文件上传时，跳过工具检测，直接将文件内容传给大模型
    tool_call = None if request.files else detect_tool_intent(request.message)
    
    def sync_stream_generator():
        full_response = ""
        tool_result = ""
        token_stats = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        try:
            if tool_call:
                tool_name = tool_call.get("tool")
                tool_desc = {"exec": "执行命令", "read_file": "读取文件", "list_dir": "列出目录", "search": "网页搜索", "script_create": "创建脚本", "script_execute": "执行脚本", "script_list": "列出脚本", "generate_pdf": "生成PDF"}.get(tool_name, tool_name)
                tool_header = "\n🔧 正在执行工具: " + tool_desc + "...\n\n"
                yield f"data: {json.dumps({'success': True, 'content': tool_header, 'session_id': session_id})}\n\n"
                
                tool_result = execute_tool_call(tool_call)
                
                if tool_result:
                    result_header = "📋 工具执行结果:\n" + tool_result + "\n\n---\n\n"
                    yield f"data: {json.dumps({'success': True, 'content': result_header, 'session_id': session_id})}\n\n"
            
            context = session["messages"][-10:]
            
            memory_context = ""
            keywords = memory_manager.extract_keywords(request.message, max_keywords=8)
            if keywords:
                long_term_memories = memory_manager.retrieve_by_keywords(keywords, memory_type='long_term', limit=5)
                short_term_memories = memory_manager.retrieve_by_keywords(keywords, memory_type='short_term', limit=5)
                
                all_memories = long_term_memories + short_term_memories
                
                if all_memories:
                    memory_context = "\n\n📚 根据历史对话，以下信息可能对回答有帮助：\n"
                    for i, memory in enumerate(all_memories[:8], 1):
                        mem_type = {"long_term": "长期记忆", "short_term": "短期记忆"}.get(memory['type'], memory['type'])
                        weight_info = f" (权重: {memory.get('weight', 1.0):.1f})" if memory.get('weight') else ""
                        memory_context += f"{i}. [{mem_type}{weight_info}] {memory['content']}\n"

            # 知识库RAG检索
            knowledge_context = ""
            try:
                kb_results = knowledge_base.search(request.message, top_k=5, threshold=0.3)
                if kb_results:
                    knowledge_context = "\n\n📄 知识库参考：\n"
                    for i, result in enumerate(kb_results, 1):
                        source = result.get('filename', '未知文档')
                        score = result.get('score', 0)
                        content = result.get('content', '')
                        knowledge_context += f"{i}. [来源: {source} | 相似度: {score:.2f}] {content}\n"
            except Exception as e:
                print(f"[RAG] 知识库检索失败: {e}")

            if tool_result:
                user_content = f"""用户问题: {request.message}

我已经为你执行了相关工具，以下是工具执行结果：

{tool_result}

{memory_context}{knowledge_context}

请基于上述工具执行结果、记忆信息和知识库参考，为用户提供详细的分析和解答。
如果你无法直接通过文字完成用户的任务，请在回复开头添加 [NEED_SCRIPT] 标记。"""
            else:
                user_content = f"""用户问题: {request.message}

{memory_context}{knowledge_context}

请基于上述记忆信息和知识库参考，为用户提供详细的解答。
如果你无法直接通过文字完成用户的任务（例如需要计算、数据处理、文件操作、系统检查等），请在回复开头添加 [NEED_SCRIPT] 标记，系统会自动生成并执行Python脚本来完成任务。"""
            
            messages = adapter.create_prompt(system_prompt, user_content, context)
            
            for chunk in adapter.chat_stream(messages):
                if isinstance(chunk, dict):
                    content = chunk.get("content", "")
                    if chunk.get("usage"):
                        token_stats = chunk["usage"]
                else:
                    content = str(chunk)
                
                if content and not content.startswith("{\"__stats__\""):
                    full_response += content
                    yield f"data: {json.dumps({'success': True, 'content': content, 'session_id': session_id})}\n\n"
            
            import time
            time.sleep(0.1)
            
            from llm.model_call_logger import model_call_logger
            recent_logs = model_call_logger.call_logs
            if recent_logs:
                latest_log = recent_logs[-1]
                token_stats = {
                    "prompt_tokens": latest_log.prompt_tokens,
                    "completion_tokens": latest_log.completion_tokens,
                    "total_tokens": latest_log.total_tokens,
                    "tokens_per_second": latest_log.tokens_per_second
                }
            
            # 检测是否需要创建脚本（有文件上传时不生成脚本）
            if not request.files:
                need_script = "[NEED_SCRIPT]" in full_response
                if need_script:
                    # 移除标记，不展示给用户
                    full_response = full_response.replace("[NEED_SCRIPT]", "").strip()
                    # 从LLM回复中提取任务描述，用于生成脚本
                    script_task = request.message
                    
                    yield "data: " + json.dumps({'success': True, 'content': '\n\n🔧 检测到需要编写脚本完成任务，正在生成...\n', 'session_id': session_id}) + "\n\n"
                    
                    # 调用脚本生成
                    script_code, script_name, script_desc = generate_script_code(script_task)
                    
                    if script_code:
                        syntax_result = check_script_syntax(script_code)
                        if syntax_result["success"]:
                            save_script_to_file(script_name, script_code)
                            script_manager.create_script(script_name, script_code, description=script_desc, is_approved=True)
                            
                            script_info = '✅ 脚本已生成并保存到脚本库\n📝 脚本: ' + script_name + '（' + script_desc + '）\n\n正在执行...\n'
                            yield "data: " + json.dumps({'success': True, 'content': script_info, 'session_id': session_id}) + "\n\n"
                            
                            # 执行脚本
                            exec_result = execute_python_script(script_code)
                            exec_result_str = exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
                            
                            # 将执行结果交给LLM解读
                            yield "data: " + json.dumps({'success': True, 'content': '📋 执行结果:\n\n', 'session_id': session_id}) + "\n\n"
                            
                            # 调用LLM解读执行结果
                            interpret_prompt = '用户问题: ' + request.message + '\n\n我编写并执行了一个Python脚本来完成这个任务。\n\n脚本名称: ' + script_name + '\n脚本描述: ' + script_desc + '\n\n执行结果:\n' + exec_result_str + '\n\n请基于执行结果，为用户提供详细的分析和解答。'
                            
                            interpret_messages = adapter.create_prompt(
                                "你是龙虾Claw，一个强大的AI智能体助手。请基于脚本执行结果为用户提供详细的解读。",
                                interpret_prompt, []
                            )
                            
                            for chunk in adapter.chat_stream(interpret_messages):
                                if isinstance(chunk, dict):
                                    content = chunk.get("content", "")
                                else:
                                    content = str(chunk)
                                if content and not content.startswith("{\"__stats__\""):
                                    yield "data: " + json.dumps({'success': True, 'content': content, 'session_id': session_id}) + "\n\n"
                            
                            full_response = full_response + "\n\n📋 脚本执行结果:\n" + exec_result_str
                        else:
                            error_msg = '❌ 脚本语法错误:\n\n' + syntax_result["error"]
                            yield "data: " + json.dumps({'success': True, 'content': error_msg, 'session_id': session_id}) + "\n\n"
                    else:
                        yield "data: " + json.dumps({'success': True, 'content': '❌ 脚本生成失败，请重试', 'session_id': session_id}) + "\n\n"
            
            final_response = full_response
            if tool_result:
                final_response = f"🔧 工具执行结果:\n{tool_result}\n\n---\n\n{full_response}"
            
            session["messages"].append({"role": "assistant", "content": final_response, "timestamp": datetime.now().isoformat()})
            if len(session["messages"]) > MAX_CHAT_HISTORY:
                session["messages"] = session["messages"][-MAX_CHAT_HISTORY:]
            
            response_keywords = memory_manager.extract_keywords(full_response, max_keywords=8)
            
            combined_keywords = keywords + response_keywords
            
            short_term_content = f"对话记录: 用户问 '{request.message}', AI回答要点: {full_response[:150]}"
            memory_manager.store('short_term', short_term_content, 
                               keywords=combined_keywords, 
                               session_id=session_id,
                               weight=1.0)
            
            if len(request.message) > 8 and len(full_response) > 20:
                important_facts = extract_important_facts(request.message, full_response)
                for fact in important_facts[:3]:
                    long_term_content = f"重要事实: {fact}"
                    memory_manager.store('long_term', long_term_content,
                                       keywords=memory_manager.extract_keywords(fact),
                                       session_id=session_id,
                                       weight=1.5)
            
            yield f"data: {json.dumps({'success': True, 'content': '', 'session_id': session_id, 'done': True, 'model_name': adapter.model_name, 'token_stats': token_stats})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'success': False, 'error': str(e), 'session_id': session_id})}\n\n"
    
    return StreamingResponse(sync_stream_generator(), media_type="text/event-stream")

@router.get("/chat/sessions")
async def chat_sessions_list():
    sessions_info = []
    for session_id, session in chat_sessions.items():
        sessions_info.append({
            "id": session_id,
            "message_count": len(session["messages"]),
            "created_at": session["created_at"],
            "last_used": session["last_used"],
            "preview": session["messages"][-1]["content"][:50] if session["messages"] else ""
        })
    return {"success": True, "sessions": sessions_info}

@router.get("/chat/session/{session_id}")
async def chat_session_detail(session_id: str):
    session = chat_sessions.get(session_id)
    if not session:
        return {"success": False, "error": "会话不存在"}
    return {"success": True, "session": session}

@router.delete("/chat/session/{session_id}")
async def chat_session_delete(session_id: str):
    if session_id in chat_sessions:
        del chat_sessions[session_id]
        return {"success": True, "message": "会话已删除"}
    return {"success": False, "error": "会话不存在"}

@router.delete("/chat/sessions")
async def chat_sessions_clear():
    chat_sessions.clear()
    return {"success": True, "message": "所有会话已清空"}

def exec_cmd(command: str) -> str:
    cmd_lower = command.strip().lower().split()[0] if command.strip() else ""
    if cmd_lower in DANGEROUS_COMMANDS:
        return f"❌ 危险命令禁止执行: {cmd_lower}"
    if cmd_lower and cmd_lower not in ALLOWED_COMMANDS:
        return f"❌ 命令不在允许列表中: {cmd_lower}"
    try:
        result = subprocess.run(command, shell=True, timeout=30, capture_output=True, text=True, cwd=str(BASE_DIR))
        output = ""
        if result.stdout:
            output += f"标准输出:\n{result.stdout}\n"
        if result.stderr:
            output += f"错误输出:\n{result.stderr}\n"
        if result.returncode != 0:
            output += f"返回码: {result.returncode}"
        if not output:
            output = "命令执行完成，无输出"
        return f"```bash\n{command}\n```\n\n执行结果:\n{output}"
    except subprocess.TimeoutExpired:
        return f"❌ 命令执行超时 (30秒)"
    except Exception as e:
        return f"❌ 命令执行失败: {str(e)}"

def read_file(path: str) -> str:
    try:
        file_path = Path(path).resolve()
        allowed = False
        for allowed_path in ALLOWED_PATHS:
            if str(file_path).startswith(allowed_path):
                allowed = True
                break
        if not allowed:
            return f"❌ 无权访问该文件: {path}"
        if not file_path.exists():
            return f"❌ 文件不存在: {path}"
        if not file_path.is_file():
            return f"❌ 路径不是文件: {path}"
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"```\n{content}\n```"
    except Exception as e:
        return f"❌ 读取文件失败: {str(e)}"

def list_dir(path: str = ".") -> str:
    try:
        dir_path = Path(path).resolve()
        allowed = False
        for allowed_path in ALLOWED_PATHS:
            if str(dir_path).startswith(allowed_path):
                allowed = True
                break
        if not allowed:
            return f"❌ 无权访问该目录: {path}"
        if not dir_path.exists():
            return f"❌ 目录不存在: {path}"
        if not dir_path.is_dir():
            return f"❌ 路径不是目录: {path}"
        items = []
        for item in sorted(dir_path.iterdir()):
            if item.is_file():
                size = item.stat().st_size
                items.append(f"📄 {item.name} ({size} bytes)")
            elif item.is_dir():
                items.append(f"📁 {item.name}/")
        return "\n".join(items) if items else "目录为空"
    except Exception as e:
        return f"❌ 列出目录失败: {str(e)}"

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

import re

def execute_tools_in_response(content: str) -> str:
    pattern = r'\[tool:(\w+)\(([^)]+)\)\]'
    matches = re.findall(pattern, content)
    
    for match in matches:
        tool_name = match[0]
        params_str = match[1]
        
        params = {}
        for param in params_str.split(','):
            param = param.strip()
            if '=' in param:
                key, value = param.split('=', 1)
                params[key.strip()] = value.strip().strip('"\'')
        
        result = ""
        if tool_name == "exec":
            result = exec_cmd(params.get("command", ""))
        elif tool_name == "read_file":
            result = read_file(params.get("path", ""))
        elif tool_name == "list_dir":
            result = list_dir(params.get("path", "."))
        elif tool_name == "search":
            result = web_search(params.get("query", ""), int(params.get("num", 5)))
        
        if result:
            content = content.replace(f"[tool:{tool_name}({params_str})]", f"\n\n工具执行结果:\n{result}")
    
    return content

def detect_tool_intent(message: str) -> dict:
    """检测用户消息中的工具调用意图，返回工具调用信息"""
    msg_lower = message.lower()
    
    # PDF生成模式（优先检测）
    pdf_patterns = [
        r'(?:生成|创建|制作)(?:pdf|文档)(?:文件)?[：:\s]*(.+)',
        r'(?:生成|创建|制作)(?:pdf|文档)(?:文件)?',
        r'(?:pdf|文档)(?:生成|创建|制作)(?:文件)?',
    ]
    
    for pattern in pdf_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            content = m.group(1).strip() if m.lastindex else message
            return {"tool": "generate_pdf", "content": content}
    
    exec_patterns = [
        r'执行(?:命令|shell|cmd)[：:\s]*(.+)',
        r'运行(?:命令)?[：:\s]*(.+)',
        r'(?:执行|运行|跑)\s*[`"]([^`"]+)[`"]',
        r'命令[：:\s]*(.+)',
    ]
    list_dir_patterns = [
        r'(?:列出|显示|查看)(?:当前)?(?:目录|文件夹)(?:下(?:的)?(?:文件|内容))?',
        r'(?:列出|显示|查看)(.+?)(?:目录|文件夹)(?:下(?:的)?(?:文件|内容))?',
        r'list\s+dir',
        r'ls\s+(.+)',
    ]
    read_file_patterns = [
        r'(?:读取|查看|看)(?:文件|内容)[：:\s]*(.+)',
        r'(?:读取|查看|看)\s+[`"]([^`"]+)[`"]',
        r'(?:cat|type)\s+(.+)',
    ]
    search_patterns = [
        r'(?:搜索|联网搜索|网上搜索|查一下|查询|search)[：:\s]*(.+)',
        r'(?:搜索|查一下|查询)\s+(.+)',
    ]
    script_patterns = [
        r'(?:编写|写一个|创建|保存)\s*(.+?)\s*(?:脚本|python脚本)',
        r'(?:写一个|创建)(?:脚本)?[：:\s]*(.+)',
        r'(?:执行|运行|运行脚本)(?:脚本)?[：:\s]*(\d+)',
        r'(?:执行|运行)\s*(脚本)',
        r'(?:运行|执行)\s*python\s+(.+)',
        r'(?:python)\s+(.+)',
    ]
    
    # 优先匹配脚本模式
    for pattern in script_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            if "编写" in msg_lower or "写一个" in msg_lower or "创建" in msg_lower or "保存" in msg_lower:
                return {"tool": "script_create", "code": message}
            elif m.group(1).isdigit():
                return {"tool": "script_execute", "script_id": int(m.group(1))}
            else:
                code = message.replace("执行脚本", "").replace("运行脚本", "").replace("执行", "").replace("运行", "").strip()
                if code.startswith("python"):
                    code = code[6:].strip()
                return {"tool": "script_execute", "code": code}
    
    for pattern in exec_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            cmd = m.group(1).strip().strip('`"\'')
            for allowed in ALLOWED_COMMANDS:
                if cmd.lower().startswith(allowed):
                    return {"tool": "exec", "command": cmd}
            return {"tool": "exec", "command": cmd}
    
    for pattern in list_dir_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            path = m.group(1).strip() if m.lastindex else "."
            if path in ["目录", "文件夹", "当前", ""]:
                path = "."
            return {"tool": "list_dir", "path": path}
    
    for pattern in read_file_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            path = m.group(1).strip().strip('`"\'')
            return {"tool": "read_file", "path": path}
    
    for pattern in search_patterns:
        m = re.search(pattern, message)
        if m:
            query = m.group(1).strip().strip('`"\'')
            return {"tool": "search", "query": query}
    
    keywords_map = {
        "list_dir": ["列出文件", "列出目录", "查看目录", "显示文件", "目录结构", "有哪些文件"],
        "search": ["搜索一下", "帮我搜", "网上查", "联网查", "最新信息", "search for"],
        "read_file": ["读取文件", "看下文件", "文件内容"],
        "exec": ["执行命令", "运行命令", "shell命令"],
        "script_list": ["列出脚本", "查看脚本", "有哪些脚本"],
        "script_execute": ["运行脚本", "执行脚本"],
    }
    
    for tool, keywords in keywords_map.items():
        for kw in keywords:
            if kw in msg_lower:
                if tool == "list_dir":
                    return {"tool": "list_dir", "path": "."}
                elif tool == "search":
                    return {"tool": "search", "query": message}
                elif tool == "exec":
                    return {"tool": "exec", "command": message}
                elif tool == "read_file":
                    return {"tool": "read_file", "path": message}
                elif tool == "script_list":
                    return {"tool": "script_list"}
                elif tool == "script_execute":
                    return {"tool": "script_execute", "code": message}
    
    return None

def execute_tool_call(tool_call: dict) -> str:
    """执行工具调用，返回结果字符串"""
    tool = tool_call.get("tool")
    
    if tool == "generate_pdf":
        content = tool_call.get("content", "")
        title = "文档"
        
        # 从内容中提取标题
        lines = content.split('\n')
        if lines:
            first_line = lines[0].strip()
            # 如果第一行较短，可能是标题
            if len(first_line) < 30 and len(lines) > 1:
                title = first_line
                content = '\n'.join(lines[1:]).strip()
        
        # 调用PDF生成函数
        try:
            # 检查fpdf2是否安装
            try:
                import fpdf
            except ImportError:
                packages_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'packages')
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
            filepath = os.path.join(LOBSTER_CLAW_FILES_DIR, filename)
            pdf.output(filepath)
            
            download_url = f"/api/lobster-claw/script/files/download/{filename}"
            
            return f"✅ PDF文件已生成！\n\n📄 文件名: {filename}\n📝 标题: {title}\n📥 下载链接: http://localhost:8888{download_url}\n🔤 使用字体: {font_path if font_path else 'Arial (无中文字体)'}"
        
        except Exception as e:
            return f"❌ PDF生成失败: {str(e)}"
    
    if tool == "exec":
        return exec_cmd(tool_call.get("command", ""))
    elif tool == "read_file":
        return read_file(tool_call.get("path", ""))
    elif tool == "list_dir":
        return list_dir(tool_call.get("path", "."))
    elif tool == "search":
        return web_search(tool_call.get("query", ""), int(tool_call.get("num", 5)))
    elif tool == "script_create":
        code = tool_call.get("code", "")
        
        # 调用LLM生成脚本代码、英文名称和中文描述
        script_code, script_name, script_desc = generate_script_code(code)
        
        if not script_code:
            return "❌ 脚本生成失败，请重试"
        
        # 检查语法
        syntax_result = check_script_syntax(script_code)
        
        if syntax_result["success"]:
            # 保存到文件系统和脚本库
            save_script_to_file(script_name, script_code)
            script_manager.create_script(script_name, script_code, description=script_desc, is_approved=True)
            
            # 执行并返回结果
            exec_result = execute_python_script(script_code)
            exec_result_str = exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
            return exec_result_str
        else:
            return f"❌ 脚本语法错误:\n\n{syntax_result['error']}\n\n请修改需求后重新尝试。"
    elif tool == "script_execute":
        script_id = tool_call.get("script_id")
        code = tool_call.get("code", "")
        
        if script_id:
            script = script_manager.get_script(script_id)
            if script:
                exec_result = execute_python_script(script["code"])
                return exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
            else:
                return f"❌ 脚本不存在，ID: {script_id}"
        elif code:
            exec_result = execute_python_script(code)
            return exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
        else:
            return "❌ 请提供脚本ID或脚本代码"
    elif tool == "script_list":
        scripts = script_manager.list_scripts()
        if not scripts:
            return "📋 暂无脚本"
        result = "📋 脚本列表:\n"
        for script in scripts:
            result += f"\nID: {script['id']}\n名称: {script['name']}\n描述: {script.get('description', '无')}\n创建时间: {script['created_at'][:19].replace('T', ' ')}\n"
        return result
    
    return ""

class MemoryAddRequest(BaseModel):
    content: str
    memory_type: str = "long_term"
    keywords: Optional[List[str]] = None
    session_id: Optional[str] = None

class MemorySearchRequest(BaseModel):
    query: str
    memory_type: Optional[str] = None
    limit: int = 10

@router.get("/memory/list")
async def memory_list(memory_type: Optional[str] = None, limit: int = 100):
    memories = memory_manager.get_all(memory_type=memory_type, limit=limit)
    return {"success": True, "memories": memories, "count": len(memories)}

@router.post("/memory/add")
async def memory_add(request: MemoryAddRequest):
    try:
        memory_id = memory_manager.store(
            memory_type=request.memory_type,
            content=request.content,
            keywords=request.keywords,
            session_id=request.session_id
        )
        return {"success": True, "message": "记忆已添加", "memory_id": memory_id}
    except ValueError as e:
        return {"success": False, "error": str(e)}

@router.delete("/memory/{memory_id}")
async def memory_delete(memory_id: int):
    success = memory_manager.delete(memory_id)
    if success:
        return {"success": True, "message": "记忆已删除"}
    return {"success": False, "error": "记忆不存在"}

@router.post("/memory/search")
async def memory_search(request: MemorySearchRequest):
    memories = memory_manager.retrieve(
        query=request.query,
        memory_type=request.memory_type,
        limit=request.limit
    )
    return {"success": True, "memories": memories, "count": len(memories)}

@router.delete("/memory/clear")
async def memory_clear(memory_type: str):
    count = memory_manager.clear(memory_type)
    return {"success": True, "message": f"已清空 {count} 条记忆"}


# ============ 知识库管理 API ============

class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    threshold: float = 0.3

@router.post("/knowledge/upload")
async def knowledge_upload(files: List[UploadFile] = File(...)):
    """上传文档到知识库"""
    from models.model_manager import ModelManager
    knowledge_base.set_model_manager(ModelManager())

    results = []
    for file in files:
        try:
            file_ext = Path(file.filename).suffix
            upload_dir = BASE_DIR / "web" / "static" / "uploads" / "claw"
            upload_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_name = f"{timestamp}_{os.urandom(8).hex()}{file_ext}"
            file_path = upload_dir / unique_name

            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)

            result = knowledge_base.add_document(str(file_path), file.filename, len(content))
            results.append({
                'success': True,
                'doc_id': result['doc_id'],
                'filename': file.filename,
                'chunk_count': result['chunk_count'],
                'file_size': result['file_size']
            })
        except ValueError as e:
            results.append({'success': False, 'filename': file.filename, 'error': str(e)})
        except Exception as e:
            results.append({'success': False, 'filename': file.filename, 'error': str(e)})

    return {"success": all(r.get('success') for r in results), "results": results}

@router.get("/knowledge/list")
async def knowledge_list():
    """获取知识库文档列表"""
    return {"success": True, "data": knowledge_base.list_documents()}

@router.delete("/knowledge/{doc_id}")
async def knowledge_delete(doc_id: str):
    """删除知识库文档"""
    deleted = knowledge_base.delete_document(doc_id)
    return {"success": True, "message": f"已删除文档，清理了 {deleted} 个分块"}

@router.post("/knowledge/search")
async def knowledge_search(request: KnowledgeSearchRequest):
    """语义搜索知识库"""
    from models.model_manager import ModelManager
    knowledge_base.set_model_manager(ModelManager())

    try:
        results = knowledge_base.search(request.query, top_k=request.top_k, threshold=request.threshold)
        return {"success": True, "data": results}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/knowledge/stats")
async def knowledge_stats():
    """获取知识库统计信息"""
    return {"success": True, "data": knowledge_base.get_stats()}


# ============ 脚本管理功能 ============
import tempfile
import sys
from io import StringIO

class ScriptCreateRequest(BaseModel):
    name: str
    code: str
    description: str = ""

class ScriptExecuteRequest(BaseModel):
    script_id: Optional[int] = None
    code: Optional[str] = None

@router.post("/script/create")
async def script_create(request: ScriptCreateRequest):
    script = script_manager.create_script(request.name, request.code, request.description)
    result = {"success": True, "message": "脚本创建成功", "script": script}
    add_to_history(f"script_create {request.name}", result)
    return result

@router.get("/script/list")
async def script_list():
    scripts = script_manager.list_scripts()
    return {"success": True, "scripts": scripts}

@router.get("/script/{script_id}")
async def script_get(script_id: int):
    script = script_manager.get_script(script_id)
    if script:
        return {"success": True, "script": script}
    return {"success": False, "error": "脚本不存在"}

@router.put("/script/{script_id}")
async def script_update(script_id: int, request: ScriptCreateRequest):
    script = script_manager.update_script(script_id, request.name, request.code, request.description)
    if script:
        result = {"success": True, "message": "脚本更新成功", "script": script}
        add_to_history(f"script_update {script_id}", result)
        return result
    return {"success": False, "error": "脚本不存在"}

@router.delete("/script/{script_id}")
async def script_delete(script_id: int):
    success = script_manager.delete_script(script_id)
    if success:
        result = {"success": True, "message": "脚本删除成功"}
        add_to_history(f"script_delete {script_id}", result)
        return result
    return {"success": False, "error": "脚本不存在"}

@router.post("/script/{script_id}/approve")
async def script_approve(script_id: int):
    """审批脚本，允许执行包含危险操作的脚本"""
    script = script_manager.approve_script(script_id)
    if script:
        result = {"success": True, "message": "脚本审批成功，已授权执行"}
        add_to_history(f"script_approve {script_id}", result)
        return result
    return {"success": False, "error": "脚本不存在"}

@router.post("/script/{script_id}/revoke")
async def script_revoke(script_id: int):
    """撤销脚本审批"""
    script = script_manager.revoke_script(script_id)
    if script:
        result = {"success": True, "message": "脚本审批已撤销"}
        add_to_history(f"script_revoke {script_id}", result)
        return result
    return {"success": False, "error": "脚本不存在"}

def check_script_syntax(code: str) -> dict:
    """检查脚本语法是否正确"""
    try:
        compile(code, '<string>', 'exec')
        return {"success": True}
    except SyntaxError as e:
        return {"success": False, "error": f"{e.msg} (行 {e.lineno})\n\n{e.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def save_script_to_file(script_name: str, script_code: str) -> str:
    """保存脚本到文件系统"""
    # 创建脚本目录（如果不存在）
    scripts_dir = Path(BASE_DIR) / "web" / "static" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成文件名（去除特殊字符）
    safe_name = re.sub(r'[\\/:*?"<>|]', '', script_name)
    if not safe_name:
        safe_name = "unnamed"
    
    # 检查文件名是否已存在，添加序号
    base_name = safe_name
    counter = 1
    while True:
        file_name = f"{safe_name}.py"
        file_path = scripts_dir / file_name
        if not file_path.exists():
            break
        safe_name = f"{base_name}_{counter}"
        counter += 1
    
    # 写入文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(script_code)
    
    return str(file_path)

def generate_script_code(requirements: str) -> tuple:
    """根据用户需求调用LLM生成Python脚本代码，返回(脚本代码, 英文名称, 中文描述)"""
    try:
        adapter = get_default_llm_adapter("shineyue")
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
        import re
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


def get_pip_package_name(import_name: str) -> str:
    """将import名转换为pip包名"""
    return IMPORT_TO_PIP.get(import_name, import_name)


def detect_missing_dependencies(code: str) -> List[str]:
    """检测脚本中缺失的第三方依赖"""
    # 添加packages目录到sys.path，确保能检测到安装的包
    packages_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'packages')
    if packages_dir not in sys.path:
        sys.path.insert(0, packages_dir)
    
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


def install_package_sync(package_name: str) -> Dict[str, Any]:
    """同步安装Python包（用于后台线程）"""
    global installation_state
    
    installation_state.update({
        'in_progress': True,
        'package': package_name,
        'progress': 0,
        'output': '',
        'success': False
    })
    
    try:
        # 执行安装（增加超时时间到300秒，支持大库安装）
        # 使用 --target 参数安装到项目目录下的 packages 文件夹，避免权限不足问题
        packages_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'packages')
        os.makedirs(packages_dir, exist_ok=True)
        
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
                '--target', packages_dir, 
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
                    timeout=600  # 增加超时时间到10分钟
                )
                
                if result.returncode == 0:
                    break  # 安装成功，退出循环
                
                last_error = result.stderr
                installation_state['output'] = f"镜像源 {index_url} 安装失败，尝试下一个...\n{result.stderr}"
                
            except subprocess.TimeoutExpired:
                last_error = f"镜像源 {index_url} 超时，尝试下一个..."
                installation_state['output'] = last_error
                continue
        
        if result is None:
            # 所有镜像源都失败了
            installation_state['output'] = f"所有镜像源安装失败: {last_error}"
            return {
                'success': False,
                'message': f'包 {package_name} 安装失败，所有镜像源均无法使用',
                'output': last_error or '未知错误'
            }
        
        installation_state['output'] = result.stdout + result.stderr
        
        if result.returncode == 0:
            installation_state['success'] = True
            installation_state['progress'] = 100
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
        installation_state['output'] = '安装超时'
        return {
            'success': False,
            'message': f'包 {package_name} 安装超时',
            'output': '安装超时（超过120秒）'
        }
    except Exception as e:
        installation_state['output'] = str(e)
        return {
            'success': False,
            'message': f'包 {package_name} 安装出错: {str(e)}',
            'output': str(e)
        }
    finally:
        installation_state['in_progress'] = False


def install_package_async_thread(package_name: str, callback=None):
    """异步安装Python包（后台线程）"""
    def worker():
        result = install_package_sync(package_name)
        if callback:
            callback(result)
    threading.Thread(target=worker, daemon=True).start()


def execute_python_script(code: str) -> Dict[str, Any]:
    """执行Python脚本，返回执行结果和生成的文件信息"""
    # 保存临时文件执行
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name
        
        # 设置环境变量，确保子进程使用UTF-8编码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        
        # 添加packages目录到PYTHONPATH，使安装的包能被脚本找到
        packages_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'packages')
        if packages_dir not in sys.path:
            sys.path.insert(0, packages_dir)
        
        # 设置PYTHONPATH环境变量，供子进程使用
        current_pythonpath = env.get('PYTHONPATH', '')
        if current_pythonpath:
            env['PYTHONPATH'] = packages_dir + os.pathsep + current_pythonpath
        else:
            env['PYTHONPATH'] = packages_dir
        
        # 记录执行前目录中的文件
        script_dir = os.path.dirname(__file__)
        before_files = set()
        for entry in os.listdir(script_dir):
            entry_path = os.path.join(script_dir, entry)
            if os.path.isfile(entry_path):
                before_files.add(entry)
        
        # 使用subprocess执行脚本，捕获输出
        result = subprocess.run(
            ['python', '-B', temp_file],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
            cwd=script_dir,
            env=env
        )
        
        stdout_output = result.stdout
        stderr_output = result.stderr
        
        # 删除临时文件
        os.unlink(temp_file)
        
        # 检测脚本执行后新生成的文件
        generated_files = []
        for entry in os.listdir(script_dir):
            entry_path = os.path.join(script_dir, entry)
            if os.path.isfile(entry_path) and entry not in before_files:
                ext = os.path.splitext(entry)[1].lower()
                if ext in ALLOWED_FILE_EXTENSIONS:
                    # 移动文件到指定目录
                    new_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{entry}"
                    new_filepath = os.path.join(LOBSTER_CLAW_FILES_DIR, new_filename)
                    os.rename(entry_path, new_filepath)
                    
                    generated_files.append({
                        "name": new_filename,
                        "original_name": entry,
                        "size": os.path.getsize(new_filepath),
                        "download_url": f"/api/lobster-claw/script/files/download/{new_filename}"
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

@router.post("/script/check-dependencies")
async def script_check_dependencies(request: ScriptExecuteRequest):
    """检测脚本所需的依赖是否已安装"""
    try:
        code = ""
        if request.script_id:
            script = script_manager.get_script(request.script_id)
            if not script:
                return {"success": False, "error": "脚本不存在"}
            code = script["code"]
        elif request.code:
            code = request.code
        else:
            return {"success": False, "error": "请提供脚本ID或脚本代码"}
        
        missing = detect_missing_dependencies(code)
        return {
            "success": True,
            "missing_dependencies": missing,
            "has_missing": len(missing) > 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/script/install-dependency")
async def script_install_dependency(package_name: str = Form(...)):
    """安装指定的Python依赖包（异步，不阻塞事件循环）"""
    try:
        if not package_name:
            return {"success": False, "error": "请提供包名"}
        
        # 使用asyncio.to_thread避免阻塞事件循环
        result = await asyncio.to_thread(install_package_sync, package_name)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/script/install-dependency-async")
async def script_install_dependency_async(package_name: str = Form(...)):
    """异步安装指定的Python依赖包（后台执行）"""
    try:
        if not package_name:
            return {"success": False, "error": "请提供包名"}
        
        install_package_async_thread(package_name)
        return {"success": True, "message": f"正在后台安装包 {package_name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/script/installation-status")
async def script_installation_status():
    """获取依赖安装状态"""
    return installation_state


@router.get("/script/files/download/{file_name}")
async def download_script_file(file_name: str):
    """下载脚本生成的文件"""
    try:
        # 安全检查：防止路径穿越
        safe_file_name = os.path.basename(file_name)
        file_path = os.path.join(LOBSTER_CLAW_FILES_DIR, safe_file_name)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查文件扩展名是否在白名单中
        ext = os.path.splitext(safe_file_name)[1].lower()
        if ext not in ALLOWED_FILE_EXTENSIONS:
            raise HTTPException(status_code=403, detail="不允许下载此类型的文件")
        
        # 返回文件下载响应
        return StreamingResponse(
            open(file_path, "rb"),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_file_name}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.get("/script/files/list")
async def list_script_files():
    """列出所有脚本生成的文件"""
    try:
        files = []
        if os.path.exists(LOBSTER_CLAW_FILES_DIR):
            for filename in os.listdir(LOBSTER_CLAW_FILES_DIR):
                filepath = os.path.join(LOBSTER_CLAW_FILES_DIR, filename)
                if os.path.isfile(filepath):
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ALLOWED_FILE_EXTENSIONS:
                        files.append({
                            "name": filename,
                            "size": os.path.getsize(filepath),
                            "created_at": os.path.getctime(filepath),
                            "download_url": f"/api/lobster-claw/script/files/download/{filename}"
                        })
        
        # 按创建时间倒序排列
        files.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {"success": True, "files": files}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/script/execute")
async def script_execute(request: ScriptExecuteRequest):
    try:
        code = ""
        if request.script_id:
            script = script_manager.get_script(request.script_id)
            if not script:
                return {"success": False, "error": "脚本不存在"}
            code = script["code"]
        elif request.code:
            code = request.code
        else:
            return {"success": False, "error": "请提供脚本ID或脚本代码"}
        
        # 检测依赖
        missing = detect_missing_dependencies(code)
        if missing:
            return {
                "success": False,
                "error": "缺少依赖",
                "missing_dependencies": missing,
                "message": f"脚本需要安装以下依赖: {', '.join(missing)}"
            }
        
        script_result = execute_python_script(code)
        
        response = {
            "success": script_result["success"],
            "result": script_result["result"],
            "generated_files": script_result.get("generated_files", [])
        }
        add_to_history(f"script_execute", response)
        return response
    except Exception as e:
        return {"success": False, "error": str(e)}


class PdfGenerateRequest(BaseModel):
    content: str
    title: str = "文档"


@router.post("/script/generate-pdf")
async def script_generate_pdf(request: PdfGenerateRequest):
    content = request.content
    title = request.title
    """生成中文PDF文档"""
    try:
        # 检查fpdf2是否安装
        try:
            import fpdf
        except ImportError:
            # 自动安装fpdf2
            packages_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'packages')
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
            
            # 添加到sys.path
            if packages_dir not in sys.path:
                sys.path.insert(0, packages_dir)
        
        from fpdf import FPDF
        
        # 查找系统中文字体
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
        
        # 创建PDF对象
        pdf = FPDF()
        pdf.add_page()
        
        if font_path:
            font_name = 'ChineseFont'
            # 注册常规字体
            pdf.add_font(font_name, '', font_path, uni=True)
            # 尝试注册粗体字体（如果是ttc文件，需要指定索引）
            try:
                # 对于ttc字体文件，尝试用索引1作为粗体
                pdf.add_font(font_name, 'B', font_path, uni=True)
            except:
                # 如果注册粗体失败，标题就用常规字体
                pass
        else:
            font_name = 'Arial'
        
        # 设置标题（使用常规字体，避免粗体字体未注册的问题）
        pdf.set_font(font_name, '', 18)
        pdf.cell(0, 20, title, ln=True, align='C')
        
        # 设置正文
        pdf.set_font(font_name, '', 12)
        pdf.ln(10)
        
        # 处理内容
        paragraphs = content.split('\n')
        for para in paragraphs:
            para = para.strip()
            if para:
                pdf.multi_cell(0, 12, para, align='L')
                pdf.ln(5)
        
        # 保存到文件（使用英文文件名，避免中文路径问题）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"document_{timestamp}.pdf"
        filepath = os.path.join(LOBSTER_CLAW_FILES_DIR, filename)
        
        pdf.output(filepath)
        
        return {
            "success": True,
            "message": f"PDF文件已生成",
            "filename": filename,
            "original_title": title,
            "download_url": f"/api/lobster-claw/script/files/download/{filename}",
            "font_used": font_path if font_path else "Arial (无中文字体)"
        }
        
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


def extract_important_facts(user_message, ai_response):
    facts = []
    
    patterns = [
        r'([^。！？\n]+[。！？])',
        r'(\d+[\u4e00-\u9fa5]+)',
        r'([\u4e00-\u9fa5]+是[\u4e00-\u9fa5]+)',
        r'([\u4e00-\u9fa5]+可以[\u4e00-\u9fa5]+)',
        r'(推荐[\u4e00-\u9fa5]+)',
        r'(建议[\u4e00-\u9fa5]+)',
        r'(需要[\u4e00-\u9fa5]+)',
        r'(应该[\u4e00-\u9fa5]+)',
    ]
    
    import re
    for pattern in patterns:
        matches = re.findall(pattern, ai_response)
        for match in matches[:3]:
            fact = match.strip()
            if 5 <= len(fact) <= 50 and fact not in facts:
                facts.append(fact)
    
    user_keywords = memory_manager.extract_keywords(user_message, max_keywords=3)
    for keyword in user_keywords:
        if keyword in ai_response:
            for sentence in ai_response.split('。')[:5]:
                if keyword in sentence and len(sentence.strip()) > 5:
                    facts.append(sentence.strip() + '。')
    
    return list(set(facts))[:5]


# ============ 飞书接入管理 API ============
# 说明：此处使用延迟导入，避免与 web.routes.feishu 产生循环导入。
from web.routes.feishu import feishu_config, feishu_client, feishu_handler


class FeishuConfigUpdate(BaseModel):
    """飞书配置更新请求模型。

    所有字段均为可选，仅更新请求体中提供的字段。
    """
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    encrypt_key: Optional[str] = None
    verification_token: Optional[str] = None
    bot_name: Optional[str] = None
    domain: Optional[str] = None  # 'feishu' 或 'lark'
    event_mode: Optional[str] = None  # 'long_connection' 或 'webhook'
    dm_policy: Optional[str] = None  # 'open' / 'allowlist' / 'blocklist'
    allow_list: Optional[List[str]] = None
    block_list: Optional[List[str]] = None
    handle_groups: Optional[bool] = None
    handle_dms: Optional[bool] = None
    trigger_on_mention: Optional[bool] = None
    enabled: Optional[bool] = None


@router.get("/feishu/config")
async def get_feishu_config():
    """获取飞书配置（脱敏后返回）。"""
    try:
        config = feishu_config.get()
        return {
            "success": True,
            "config": config,
            "is_configured": feishu_config.is_configured(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/feishu/config")
async def update_feishu_config(request: FeishuConfigUpdate):
    """更新飞书配置（支持部分更新）。"""
    try:
        config_data = request.model_dump(exclude_none=True)
        if not config_data:
            return {"success": False, "error": "请求体未包含任何配置字段"}
        updated = feishu_config.update(config_data)
        return {
            "success": True,
            "config": updated,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/feishu/test-connection")
async def test_feishu_connection():
    """测试飞书连接（尝试获取 tenant_access_token）。"""
    try:
        if not feishu_config.is_configured():
            return {"success": False, "error": "飞书配置未完整（app_id/app_secret 缺失）"}
        token = feishu_client.get_tenant_access_token()
        if token:
            return {
                "success": True,
                "message": "连接成功",
                "token_preview": token[:20],
            }
        return {
            "success": False,
            "error": "获取 tenant_access_token 失败，请检查 app_id/app_secret 是否正确",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/feishu/status")
async def get_feishu_status():
    """获取飞书接入状态。"""
    try:
        config = feishu_config.get()
        return {
            "success": True,
            "enabled": bool(config.get("enabled", False)),
            "is_configured": feishu_config.is_configured(),
            "webhook_url": "/api/feishu/webhook",
            "bot_name": config.get("bot_name", "Lobster Bot"),
            "domain": config.get("domain", "feishu"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/feishu/messages")
async def get_feishu_messages(limit: int = 50, offset: int = 0):
    """获取飞书消息处理日志（倒序，最新在前）。"""
    try:
        messages = feishu_handler.get_message_logs(limit=limit, offset=offset)
        total = len(feishu_handler.message_logs)
        return {
            "success": True,
            "messages": messages,
            "total": total,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/feishu/messages")
async def clear_feishu_messages():
    """清空飞书消息日志。"""
    try:
        cleared = feishu_handler.clear_message_logs()
        return {"success": True, "cleared": cleared}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/feishu/sessions")
async def get_feishu_sessions():
    """获取飞书会话列表。"""
    try:
        feishu_sessions = []
        for session_id, session in chat_sessions.items():
            if session_id.startswith("feishu_"):
                is_group = session_id.startswith("feishu_group_")
                feishu_sessions.append({
                    "session_id": session_id,
                    "chat_id": session_id.replace("feishu_group_", "").replace("feishu_", ""),
                    "chat_type": "group" if is_group else "p2p",
                    "message_count": len(session.get("messages", [])),
                    "last_used": session.get("last_used", ""),
                    "is_group": is_group,
                })
        
        feishu_sessions.sort(key=lambda x: x["last_used"] or "", reverse=True)
        
        return {
            "success": True,
            "sessions": feishu_sessions,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/feishu/sessions/{session_id}")
async def get_feishu_session_detail(session_id: str):
    """获取飞书会话详情（消息列表）。"""
    try:
        session = chat_sessions.get(session_id)
        if not session or not session_id.startswith("feishu_"):
            return {"success": False, "error": "会话不存在或不是飞书会话"}
        
        is_group = session_id.startswith("feishu_group_")
        return {
            "success": True,
            "session_id": session_id,
            "chat_id": session_id.replace("feishu_group_", "").replace("feishu_", ""),
            "chat_type": "group" if is_group else "p2p",
            "messages": session.get("messages", []),
            "last_used": session.get("last_used", ""),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
