"""Multi-Agent Document Enhancer Web Server"""
import os
import asyncio
import sys
import json
import logging
from datetime import datetime

# 用户依赖目录 packages/ 只能“补充”系统包，绝不能“覆盖”——故用 append 而非 insert(0)。
# 否则用户安装的不兼容包（如需要 X86_V2 的 numpy）会顶掉系统包，导致主进程 import 失败、服务起不来。
_packages_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'packages')
if _packages_dir not in sys.path:
    sys.path.append(_packages_dir)

from utils.logger import setup_logging, logger
setup_logging()


def get_client_ip(request) -> str:
    """获取真实客户端 IP：经 nginx 反代时优先读转发头（X-Real-IP 最可信），
    其次 X-Forwarded-For 最左，最后回退直连 IP。"""
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from starlette.websockets import WebSocketState
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from agents.agent_manager import AgentManager
from models.model_manager import ModelManager
from attachment.attachment_manager import AttachmentManager
from engine.iteration_controller import IterationController
from engine.agent_worker import create_llm_adapter
from search.search_manager import SearchManager
from applogging.log_manager import LogManager
from skills.skill_manager import SkillManager
from skills.skill_executor import SkillExecutor
from web.schemas import ProcessRequest

from web.routes import models as models_router
from web.routes import agents as agents_router
from web.routes import search as search_router
from web.routes import skills as skills_router
from web.routes import attachments as attachments_router
from web.routes import system as system_router
from web.routes import image as image_router
from web.routes import video as video_router
from web.routes import ai_chat as ai_chat_router
from web.routes import lobster_claw as lobster_claw_router
from web.routes import lobster_mu as lobster_mu_router
from web.routes import feishu as feishu_router
from web.auth import require_auth

logger.info("Initializing FastAPI app...")

def _sandbox_startup_check():
    """沙箱启动自检（spec §5.2）：
    - prod（LOBSTER_ENV=prod 或运行于 docker-compose 容器内）+ fallback=warn → 拒绝启动
    - ENABLED=false → 输出显著告警
    - 配置错误（SandboxConfigError）→ 拒绝启动
    """
    try:
        from lobster_mu import sandbox_config
        cfg = sandbox_config.config
    except Exception as e:
        logger.error(f"[沙箱] 配置加载失败，拒绝启动: {e}")
        raise SystemExit(f"沙箱配置错误，服务无法启动: {e}")

    # 判定是否 prod：显式 LOBSTER_ENV=prod，或容器内有 docker-compose 运行标志
    env_flag = os.environ.get("LOBSTER_ENV", "").strip().lower()
    in_container = os.path.exists("/.dockerenv")
    is_prod = (env_flag == "prod") or (in_container and env_flag != "dev")

    if is_prod and cfg.fallback == "warn":
        logger.error("[沙箱] 配置错误：prod 环境禁止 SANDBOX_FALLBACK=warn，请改为 deny")
        raise SystemExit("prod 环境 LOBSTER_SANDBOX_FALLBACK 必须为 deny，服务无法启动")

    if not cfg.enabled:
        logger.warning("=" * 60)
        logger.warning("[沙箱] 沙箱已禁用（LOBSTER_SANDBOX_ENABLED=false）")
        logger.warning("[沙箱] 所有用户命令将在宿主机直接执行，存在安全风险！")
        logger.warning("=" * 60)

    logger.info(
        f"[沙箱] 配置: enabled={cfg.enabled}, mode={cfg.mode}, image={cfg.image}, "
        f"fallback={cfg.fallback}, admin_mode={cfg.admin_mode}, network={cfg.network}"
    )


# 启动定时任务调度器和飞书长连接
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 沙箱配置自检（§5.2）：prod+warn 组合拒绝启动；ENABLED=false 显著告警
    _sandbox_startup_check()

    logger.info("Starting cron scheduler...")
    await lobster_claw_router.cron_scheduler.start()

    logger.info("Starting mu cron scheduler...")
    await lobster_mu_router.mu_scheduler.start()

    logger.info("Starting Feishu long connection client...")
    await feishu_router.start_feishu_ws_client()

    logger.info("Warming up knowledge embedding model in background...")
    import threading as _threading
    def _kb_warmup():
        try:
            from lobster_mu import knowledge_store
            knowledge_store.warmup()
            logger.info("Knowledge embedding model warmup done")
        except Exception as e:
            logger.warning(f"Knowledge embedding model warmup failed: {e}")
    _threading.Thread(target=_kb_warmup, daemon=True).start()

    # 定期清理登录限流器的过期记录（防内存泄漏）
    import asyncio as _asyncio
    async def _limiter_cleanup():
        from web.routes.lobster_mu import login_limiter
        while True:
            await _asyncio.sleep(300)  # 每 5 分钟清理一次
            login_limiter.cleanup()
    _cleanup_task = _asyncio.create_task(_limiter_cleanup())

    # 事件循环心跳探针：每秒醒一次，若实际间隔显著大于 1s，说明事件循环被
    # 某个同步任务阻塞（表现为所有请求排队、handler 很快但整页很慢）。
    async def _loop_heartbeat():
        import time as _ht
        import sys as _sys
        import traceback as _tb
        while True:
            _t = _ht.perf_counter()
            await _asyncio.sleep(1)
            _gap = _ht.perf_counter() - _t
            if _gap > 3.0:
                logger.warning(
                    "[loop-block] 事件循环被阻塞 %.1fs（预期 1s）；"
                    "此刻所有并发请求都会排队，复现慢请求请对照此刻前后日志",
                    _gap)
                # 打印所有线程调用栈，直接定位阻塞点
                for _tid, _frame in _sys._current_frames().items():
                    _stk = "".join(_tb.format_stack(_frame))
                    logger.warning("[loop-block] 线程 tid=%s 栈:\n%s", _tid, _stk)
    _heartbeat_task = _asyncio.create_task(_loop_heartbeat())

    # 定期清理知识库共享内容的无引用孤儿（每小时一次，后台线程避免阻塞事件循环）
    def _kb_gc_loop():
        import time as _time
        while True:
            _time.sleep(3600)
            try:
                from lobster_mu import knowledge_store
                n = knowledge_store.gc_orphaned_content()
                if n:
                    logger.info(f"[kb-gc] 清理孤儿内容 {n} 个")
            except Exception as e:
                logger.debug(f"[kb-gc] 清理失败: {e}")
    _threading.Thread(target=_kb_gc_loop, daemon=True).start()

    # 每小时根据首字输出速度（TTFT）自动把默认模型切换为最快的文本模型
    def _model_speed_loop():
        import time as _time
        _time.sleep(300)  # 启动后先等 5 分钟，让调用数据积累
        while True:
            try:
                from llm.model_speed_stats import apply_fastest_default
                fastest = apply_fastest_default()
                if fastest:
                    logger.info(f"[model-speed] 默认模型已切换为最快: {fastest}")
            except Exception as e:
                logger.debug(f"[model-speed] 切换失败: {e}")
            _time.sleep(3600)
    _threading.Thread(target=_model_speed_loop, daemon=True).start()

    yield

    _cleanup_task.cancel()
    _heartbeat_task.cancel()

    logger.info("Stopping cron scheduler...")
    await lobster_claw_router.cron_scheduler.stop()

    logger.info("Stopping mu cron scheduler...")
    await lobster_mu_router.mu_scheduler.stop()

    logger.info("Stopping Feishu long connection client...")
    feishu_router.stop_feishu_ws_client()

app = FastAPI(title="Multi-Agent Document Enhancer", version="1.0", lifespan=lifespan)

# CORS：允许外部页面（如 direct-login.html）跨域调用 /api/lobster-mu 接口
# "null" 用于 file:// 打开的 HTML（Origin 为 null）
from starlette.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "null"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY", "mul_agent_secret_key_2026"))


# 修改 session cookie 属性：SameSite=None + Secure，允许 file:// 跨域页面设置 cookie
# Starlette 0.52 的 SessionMiddleware 不支持 samesite 参数，用中间件拦截 Set-Cookie 头
@app.middleware("http")
async def fix_session_cookie(request, call_next):
    response = await call_next(request)
    set_cookie = response.headers.get("set-cookie", "")
    if set_cookie and "session=" in set_cookie:
        # 替换 samesite=lax → samesite=none; secure
        new_cookie = set_cookie.replace("; samesite=lax", "; samesite=none; secure")
        if new_cookie == set_cookie:
            # 如果原头没有 samesite，追加
            new_cookie = set_cookie + "; samesite=none; secure"
        response.headers["set-cookie"] = new_cookie
    return response

# ---- 接口访问日志中间件（记录 /api/lobster-mu 请求，仅管理员可查） ----
import asyncio as _asyncio
import time as _time_mod
from starlette.middleware.base import BaseHTTPMiddleware
from lobster_mu.api_log import log_api_access


class ApiAccessLogMiddleware(BaseHTTPMiddleware):
    """记录 v3 多用户模块（/api/lobster-mu）的每次 API 访问。
    日志非阻塞投递到内存队列，由后台守护线程批量落盘，不占用请求线程；
    任何异常静默吞掉，绝不影响请求。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/lobster-mu"):
            return await call_next(request)
        start = _time_mod.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            self._safe_log(request, path, 500, int((_time_mod.perf_counter() - start) * 1000))
            raise
        dur_ms = int((_time_mod.perf_counter() - start) * 1000)
        self._safe_log(request, path, response.status_code, dur_ms)
        # 慢请求同时打到主日志，便于与 handler 内 [perf] 分段计时对照：
        # 若此处很大但 handler_total 很小 => 耗时在 handler 之前（事件循环阻塞/锁等待）。
        if dur_ms > 3000:
            logger.warning("[perf] MW %s %s total=%dms (handler 内分段请见 [perf] 日志)",
                           request.method, path, dur_ms)
        return response

    def _safe_log(self, request, path: str, status: int, duration_ms: int):
        try:
            ip = get_client_ip(request)
            session = getattr(request, "session", None) or {}
            mu_user = session.get("mu_user") or {}
            username = mu_user.get("username", "")
            user_id = mu_user.get("id", 0)
            auth_type = "session" if mu_user else "anon"
            # 非阻塞投递到内存队列，由后台线程批量落盘（见 lobster_mu/api_log.py）
            log_api_access(
                request.method, path, status, duration_ms, ip, username, user_id, auth_type)
        except Exception:
            pass


app.add_middleware(ApiAccessLogMiddleware)


async def safe_send_json(websocket: WebSocket, data: dict):
    """安全发送 JSON，避免向已关闭的 WebSocket 连接发送消息"""
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(data)
    except Exception:
        pass


# 添加异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}")
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"服务器错误: {str(exc)}"}
    )

# 配置模板和静态文件
logger.info("Configuring templates and static files...")
jinja_env = Environment(
    loader=FileSystemLoader("web/templates"),
    autoescape=True,
    cache_size=0
)
app.mount("/static", StaticFiles(directory="web/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
os.makedirs("web/static/v2/assets", exist_ok=True)
app.mount("/v2/assets", StaticFiles(directory="web/static/v2/assets"), name="v2-assets")
os.makedirs("web/static/v3/assets", exist_ok=True)
app.mount("/v3/assets", StaticFiles(directory="web/static/v3/assets"), name="v3-assets")
# vite base="/" 构建后资源引用为 /assets/...（绝对根路径），
# 挂载 /assets → v3 资源目录，使 /v3 入口能加载资源。
app.mount("/assets", StaticFiles(directory="web/static/v3/assets"), name="v3-absolute-assets")

# 全局管理器
logger.info("Initializing managers...")
agent_manager = AgentManager()
model_manager = ModelManager()
attachment_manager = AttachmentManager()
search_manager = SearchManager()
logger.info(f"Search manager loaded: adapters={list(search_manager.adapters.keys())}, enabled={[s.id for s in search_manager.get_enabled()]}")
log_manager = LogManager()
skill_manager = SkillManager()
skill_executor = SkillExecutor(skill_manager, model_manager, search_manager)
logger.info(f"Skill executor search_manager: {skill_executor.search_manager is not None}, adapters={list(skill_executor.search_manager.adapters.keys()) if skill_executor.search_manager else []}")

app.state.managers = {
    "agent_manager": agent_manager,
    "model_manager": model_manager,
    "attachment_manager": attachment_manager,
    "search_manager": search_manager,
    "log_manager": log_manager,
    "skill_manager": skill_manager,
    "skill_executor": skill_executor,
}

# 全局状态
current_document = ""
processing_status = "idle"
processing_log = []
agent_results = {}  # 存储每个Agent的执行结果
selected_agent_count = 0  # 当前选择的Agent数量
settings = {
    "iterations": 1,
    "enable_search": True,
    "max_search_per_iter": 3,
}

# 全局Token统计（累计，只有清空时才重置）
global_total_prompt_tokens = 0
global_total_completion_tokens = 0
global_total_searches = 0

# 版本号（直接定义在代码中，更新时修改此值）
app_version = "v1.20260701.100000"
logger.info(f"App version: {app_version}")

# 共享状态（供路由模块通过 app.state 访问，避免循环导入）
app.state.settings = settings
app.state.controller = None
app.state.processing_log = processing_log
app.state.processing_status = processing_status
app.state.app_version = app_version

# 设置模型调用日志回调函数
def on_model_call_log(log_entry):
    """模型调用日志回调函数"""
    logger.info(f"[Token统计] 模型: {log_entry.model_name} | "
                f"输入: {log_entry.prompt_tokens} tokens | "
                f"输出: {log_entry.completion_tokens} tokens | "
                f"耗时: {log_entry.duration:.2f}s | "
                f"速度: {log_entry.tokens_per_second:.1f} tokens/s")

# 导入并设置回调
from llm.model_call_logger import model_call_logger
model_call_logger.set_log_callback(on_model_call_log)

# 注册路由
# 对外 API 统一挂 require_auth 认证（API Key 或 session）：
#   - 9 个 v1 router + lobster_claw（命令/文件/网络等高危能力）
#   - lobster_mu 自带 get_mu_user 认证，feishu webhook 自带 token 校验，均不重复挂
_API_AUTH = [Depends(require_auth)]
app.include_router(models_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(agents_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(search_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(skills_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(attachments_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(system_router.router, prefix="", dependencies=_API_AUTH)
app.include_router(image_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(video_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(ai_chat_router.router, prefix="/api", dependencies=_API_AUTH)
app.include_router(lobster_claw_router.router, prefix="", dependencies=_API_AUTH)
app.include_router(lobster_mu_router.router, prefix="")
app.include_router(feishu_router.router)

# 为 OpenAPI 文档端点（/docs、/redoc、/openapi.json）加上认证，防止接口清单对外泄露。
# FastAPI 在 app 初始化时已注册这三个端点，其依赖在 __init__ 时就编译进 dependant，
# 运行时改 route.dependencies 不生效；因此移除原路由，重新注册带 require_auth 的版本。
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse as _HTMLResponse, JSONResponse as _JSONResponse
from starlette.requests import Request as _StarletteRequest
from fastapi.responses import Response as _Response


def _secure_doc_routes():
    doc_paths = {"/docs", "/redoc", "/openapi.json"}
    kept = [r for r in app.routes if getattr(r, "path", None) not in doc_paths]
    app.routes[:] = kept  # 原地替换，保留 app 对 routes 列表的引用

    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(require_auth)])
    async def _secure_openapi():
        return _JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(require_auth)])
    async def _secure_docs():
        openapi_url = app.openapi_url
        return get_swagger_ui_html(
            openapi_url=openapi_url,
            title=f"{app.title} - Docs",
            oauth2_redirect_url="/docs/oauth2-redirect",
            init_oauth=None,
        )

    @app.get("/redoc", include_in_schema=False, dependencies=[Depends(require_auth)])
    async def _secure_redoc():
        openapi_url = app.openapi_url
        return get_redoc_html(openapi_url=openapi_url, title=f"{app.title} - ReDoc")


_secure_doc_routes()

# 初始化控制器
controller = IterationController(
    agent_manager=agent_manager,
    model_manager=model_manager,
    log_manager=log_manager,
    search_manager=search_manager if settings["enable_search"] else None,
    iterations=settings["iterations"]
)
app.state.controller = controller

logger.info("App initialized successfully")

class LoginRequest(BaseModel):
    username: str
    password: str


async def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        return None
    return user


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # 已登录非 admin → 跳 v3；已登录 admin → 跳 v1
    user = request.session.get("user") if hasattr(request, "session") else None
    if user:
        if user.get("role") == "admin":
            return RedirectResponse(url="/")
        return RedirectResponse(url="/v3")
    template = jinja_env.get_template("login.html")
    return HTMLResponse(content=template.render())


@app.post("/api/login")
async def login(request: Request, login_data: LoginRequest):
    """旧版登录端点：改为数据库验证 + 共享限流器，消除硬编码密码"""
    from web.routes.lobster_mu import ensure_db, login_limiter
    from lobster_mu import user_store
    from lobster_mu.security import verify_password

    ip = get_client_ip(request)
    login_limiter.check(ip, login_data.username)

    ensure_db()
    row = user_store.get_by_username(login_data.username)
    if not row or row["disabled"] or not verify_password(login_data.password, row["salt"], row["password_hash"]):
        login_limiter.record_failure(ip, login_data.username)
        return {"status": "error", "message": "用户名或密码错误"}

    # v1/v2 仅允许管理员登录
    if row["role"] != "admin":
        login_limiter.record_success(ip, login_data.username)
        return {"status": "error", "message": "该账号无权限访问此系统，请使用管理员账号或前往 v3 多用户版"}

    login_limiter.record_success(ip, login_data.username)
    request.session["user"] = {"username": login_data.username, "id": row["id"], "role": row["role"]}
    user_store.update_last_login(row["id"])
    return {"status": "success", "message": "登录成功"}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return {"status": "success", "message": "退出成功"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(get_current_user)):
    """主页面（v1）"""
    if not user:
        return RedirectResponse(url="/login")
    # v1 仅允许管理员访问
    if user.get("role") != "admin":
        return RedirectResponse(url="/v3")

    models = [m.to_dict() for m in model_manager.get_all()]
    
    agent_groups = {
        'text': {'name': '文本模型', 'icon': 'fa-message-square', 'color': '#3b82f6', 'css_class': 'text-group', 'agents': []},
        'image': {'name': '文生图', 'icon': 'fa-image', 'color': '#10b981', 'css_class': 'image-group', 'agents': []},
        'video': {'name': '文生视频', 'icon': 'fa-video', 'color': '#f59e0b', 'css_class': 'video-group', 'agents': []}
    }
    
    for agent in agent_manager.get_all():
        agent_dict = agent.to_dict()
        model = model_manager.get(agent.model_id)
        if model:
            agent_dict["model_type"] = model.model_type
            agent_dict["model_name"] = model.model_name
        else:
            agent_dict["model_type"] = "text"
            agent_dict["model_name"] = ""
        
        model_type = agent_dict["model_type"]
        if model_type in agent_groups:
            agent_groups[model_type]['agents'].append(agent_dict)
        else:
            agent_groups['text']['agents'].append(agent_dict)
    
    agent_groups_list = list(agent_groups.values())
    
    flat_agents = []
    for group in agent_groups_list:
        flat_agents.extend(group['agents'])
    
    search_engines = [s.to_dict() for s in search_manager.get_all()]
    template = jinja_env.get_template("index.html")
    html_content = template.render({
        "request": request,
        "models": models,
        "agents": agent_groups_list,
        "flat_agents": flat_agents,
        "search_engines": search_engines,
        "current_document": current_document,
        "processing_status": processing_status,
        "settings": settings,
        "logs": processing_log,
        "current_user": user
    })
    return HTMLResponse(content=html_content, status_code=200)


@app.get("/chat-history/{session_id}", response_class=HTMLResponse)
async def chat_history_viewer(request: Request, session_id: str):
    """独立访问聊天记录页面"""
    template = jinja_env.get_template("chat_history_viewer.html")
    return HTMLResponse(content=template.render({"session_id": session_id}))

# ============ React v2 前端路由 ============
@app.get("/v2", response_class=HTMLResponse)
@app.get("/v2/{path:path}", response_class=HTMLResponse)
async def v2_index(request: Request, user=Depends(get_current_user)):
    """React v2 前端入口（仅管理员）"""
    import os
    if not user or user.get("role") != "admin":
        return RedirectResponse(url="/v3")
    index_path = os.path.join("web", "static", "v2", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    else:
        return HTMLResponse(content="<h1>React v2 应用尚未构建</h1><p>请运行 pnpm install && pnpm build</p>", status_code=503)

# ============ React v3（多用户龙虾Claw）前端路由 ============
# 注入 window.__BASE__="/v3"，前端 BrowserRouter basename 读该值
# （main.jsx/client.js 兼容 __BASE__ 动态前缀，当前仅 /v3 入口）。
# vite base="/"，资源走绝对 /assets/... 路径。
@app.get("/v3", response_class=HTMLResponse)
@app.get("/v3/{path:path}", response_class=HTMLResponse)
async def v3_index(request: Request):
    """React v3 前端入口，注入 window.__BASE__ 供前端感知入口前缀"""
    import os, re
    index_path = os.path.join("web", "static", "v3", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(content="<h1>React v3 应用尚未构建</h1><p>请运行 pnpm build:v3</p>", status_code=503)
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 当前仅 /v3 入口，固定注入 "/v3"
    base = "/v3"
    # 注入 window.__BASE__（若 index.html 已有则替换，否则插到 </head> 前）
    inject = f'<script>window.__BASE__="{base}";</script>'
    if 'window.__BASE__' in content:
        content = re.sub(r'<script>window\.__BASE__="[^"]*";</script>', inject, content)
    elif '</head>' in content:
        content = content.replace('</head>', inject + '\n</head>')
    # 禁止 index.html 被浏览器缓存（避免旧版缓存导致 basename 不匹配）。
    # JS/CSS 文件名带 hash，仍可长期缓存（由 StaticFiles 处理）。
    return HTMLResponse(content=content, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})

# ============ 文档处理 API（保留在 web_server.py） ============

@app.post("/api/process", dependencies=[Depends(require_auth)])
async def process_document(request: ProcessRequest):
    """处理文档"""
    global current_document, processing_status, processing_log, controller

    current_document = request.content
    processing_status = "processing"
    app.state.processing_status = processing_status
    processing_log.clear()

    # 获取附件内容
    attach_content = attachment_manager.get_all_content()
    if attach_content:
        current_document = f"{current_document}\n\n{attach_content}" if current_document else attach_content

    if not current_document:
        return {"status": "error", "message": "请输入初始内容或添加附件"}

    # 检查是否有配置好的模型
    has_configured_model = any(m.api_key for m in model_manager.get_all())
    if not has_configured_model:
        return {"status": "error", "message": "请先配置至少一个模型的API密钥"}

    async def run_processing():
        global processing_status, current_document, controller, agent_results

        try:
            # 清空之前的Agent结果
            agent_results = {}

            # 获取启用的Agent列表
            enabled_agents = agent_manager.get_enabled()
            agent_names = [a.name for a in enabled_agents]

            # 获取配置好的模型列表
            configured_models = [m.name for m in model_manager.get_all() if m.api_key]

            # 创建新控制器
            controller = IterationController(
                agent_manager=agent_manager,
                model_manager=model_manager,
                log_manager=log_manager,
                search_manager=search_manager if request.enable_search else None,
                iterations=request.iterations
            )
            app.state.controller = controller

            # 设置Agent结果回调 - 详细日志记录
            def on_agent_result(result):
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")

                agent_results[result.agent_id] = {
                    "agent_id": result.agent_id,
                    "agent_name": result.agent_name,
                    "model_name": result.model_name,
                    "success": result.success,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "tokens_used": result.tokens_used,
                    "time_spent": result.time_spent,
                    "optimization_summary": result.optimization_summary,
                    "self_evaluation": result.self_evaluation,
                    "error_message": result.error_message,
                    "iteration": controller.state.current_iteration,
                    "output_length": len(result.output) if result.output else 0
                }

                # 详细日志记录
                processing_log.append(f"[{timestamp}] ▶ Agent: {result.agent_name}")
                processing_log.append(f"    模型: {result.model_name}")
                processing_log.append(f"    状态: {'✓ 成功' if result.success else '✗ 失败'}")
                processing_log.append(f"    输入Token: {result.prompt_tokens}, 输出Token: {result.completion_tokens}, 总Token: {result.tokens_used}")
                processing_log.append(f"    耗时: {result.time_spent:.2f}秒")
                processing_log.append(f"    输出长度: {len(result.output) if result.output else 0} 字符")

                if result.optimization_summary:
                    processing_log.append(f"    优化摘要: {result.optimization_summary[:500]}...")

                if result.self_evaluation:
                    processing_log.append(f"    自我评价: {result.self_evaluation[:300]}...")

                if not result.success and result.error_message:
                    processing_log.append(f"    错误信息: {result.error_message}")

                processing_log.append("")  # 空行分隔

            controller.on_agent_result = on_agent_result

            # 初始化开始时间，用于计算elapsed_time
            import time
            start_time = time.time()
            controller._start_time = start_time
            controller.state.is_running = True

            # 详细会话开始日志
            processing_log.append("=" * 60)
            processing_log.append("║           开始新会话 - Multi-Agent 文档完善系统           ║")
            processing_log.append("=" * 60)
            processing_log.append(f"▶ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            processing_log.append(f"▶ 迭代次数: {request.iterations}")
            processing_log.append(f"▶ 启用搜索: {'是' if request.enable_search else '否'}")
            if request.enable_search:
                processing_log.append(f"▶ 每轮最大搜索次数: {settings.get('max_search_per_iter', 3)}")
            processing_log.append("")
            processing_log.append("▶ 输入信息:")
            processing_log.append(f"    初始内容长度: {len(current_document)} 字符")
            processing_log.append(f"    附件数量: {len(attachment_manager.get_attachments())}")
            if attachment_manager.get_attachments():
                for attach in attachment_manager.get_attachments():
                    processing_log.append(f"      - {attach.filename} ({attach.file_type})")
            processing_log.append("")
            processing_log.append(f"▶ 启用的Agent ({len(enabled_agents)}个):")
            for i, name in enumerate(agent_names, 1):
                processing_log.append(f"    {i}. {name}")
            processing_log.append("")
            processing_log.append(f"▶ 可用模型 ({len(configured_models)}个):")
            for i, name in enumerate(configured_models, 1):
                processing_log.append(f"    {i}. {name}")
            processing_log.append("")
            processing_log.append("-" * 60)
            processing_log.append("")

            # ========== 指令分析阶段 ==========
            processing_log.append("┌" + "─" * 58 + "┐")
            processing_log.append("│  🧠 指令分析阶段开始" + " " * 36 + "│")
            processing_log.append("└" + "─" * 58 + "┘")
            processing_log.append(f"  原始指令长度: {len(current_document)} 字符")
            processing_log.append("")

            # 执行指令分析
            analyzed_document = await asyncio.to_thread(
                controller._analyze_instruction, current_document
            )

            if analyzed_document != current_document:
                processing_log.append(f"  ✓ 指令分析完成")
                processing_log.append(f"  分析结果长度: {len(analyzed_document)} 字符")
                processing_log.append(f"  Token消耗: {controller.state.total_tokens:,}")
                processing_log.append("")
                current_document = analyzed_document
            else:
                processing_log.append("  ⚠ 指令分析未生成新内容，使用原始指令")
                processing_log.append("")

            processing_log.append("-" * 60)
            processing_log.append("")

            # 记录每次迭代前的文档长度
            prev_doc_length = len(current_document)

            for iteration in range(1, request.iterations + 1):
                if processing_status == "stopped":
                    processing_log.append("")
                    processing_log.append("⚠ 用户手动停止执行")
                    break

                processing_log.append(f"┌{'─' * 58}┐")
                processing_log.append(f"│  迭代 {iteration}/{request.iterations} 开始{' '*40}│")
                processing_log.append(f"└{'─' * 58}┘")
                processing_log.append(f"  输入文档长度: {len(current_document)} 字符")
                processing_log.append("")

                # 更新当前迭代数
                controller.state.current_iteration = iteration

                # 执行迭代
                current_document = await asyncio.to_thread(
                    controller.run_iteration_sync, iteration, current_document
                )

                # 迭代完成日志
                processing_log.append("")
                processing_log.append(f"┌{'─' * 58}┐")
                processing_log.append(f"│  迭代 {iteration}/{request.iterations} 完成{' '*40}│")
                processing_log.append(f"└{'─' * 58}┘")

                # 计算文档变化
                doc_change = len(current_document) - prev_doc_length
                change_str = f"+{doc_change}" if doc_change > 0 else str(doc_change)
                processing_log.append(f"  输出文档长度: {len(current_document)} 字符 (变化: {change_str})")
                processing_log.append(f"  累计Token消耗: {controller.state.total_tokens:,}")

                elapsed = time.time() - start_time
                hh = int(elapsed // 3600)
                mm = int((elapsed % 3600) // 60)
                ss = int(elapsed % 60)
                processing_log.append(f"  已运行时长: {hh:02d}:{mm:02d}:{ss:02d}")
                processing_log.append("")

                prev_doc_length = len(current_document)

            if processing_status != "stopped":
                processing_status = "completed"
                app.state.processing_status = processing_status
                # 完成总结日志
                total_elapsed = time.time() - start_time
                hh = int(total_elapsed // 3600)
                mm = int((total_elapsed % 3600) // 60)
                ss = int(total_elapsed % 60)

                processing_log.append("=" * 60)
                processing_log.append("║              所有迭代已完成 - 会话结束                    ║")
                processing_log.append("=" * 60)
                processing_log.append(f"▶ 总耗时: {hh:02d}:{mm:02d}:{ss:02d}")
                processing_log.append(f"▶ 总Token消耗: {controller.state.total_tokens:,}")
                processing_log.append(f"▶ 最终文档长度: {len(current_document)} 字符")
                processing_log.append(f"▶ Agent执行次数: {len(agent_results)}")
                processing_log.append(f"▶ 搜索调用次数: {controller.state.search_count}")
                processing_log.append("")
                processing_log.append("▶ 各Agent执行统计:")
                for agent_id, result in agent_results.items():
                    status = "✓" if result["success"] else "✗"
                    processing_log.append(f"    {status} {result['agent_name']}: Token {result['tokens_used']}, 耗时 {result['time_spent']:.1f}s")
                processing_log.append("")
                processing_log.append("=" * 60)
            else:
                processing_status = "stopped"
                app.state.processing_status = processing_status
        except Exception as e:
            import traceback
            processing_log.append("")
            processing_log.append("╔" + "─" * 58 + "╗")
            processing_log.append("║  ✗ 执行出错                                                ║")
            processing_log.append("╚" + "─" * 58 + "╝")
            processing_log.append(f"错误信息: {str(e)}")
            processing_log.append("")
            processing_log.append("错误详情:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    processing_log.append(f"  {line}")
            processing_status = "error"
            app.state.processing_status = processing_status
        finally:
            if controller:
                controller.state.is_running = False

    asyncio.create_task(run_processing())
    return {"status": "success", "message": "处理已开始"}

@app.post("/api/stop", dependencies=[Depends(require_auth)])
async def stop_processing():
    """停止处理"""
    global processing_status
    processing_status = "stopped"
    app.state.processing_status = processing_status
    controller.stop()
    return {"status": "success", "message": "已停止处理"}

@app.get("/api/status", dependencies=[Depends(require_auth)])
async def get_status():
    """获取处理状态"""
    # 实时更新运行时长
    if controller.state.is_running and controller._start_time:
        import time
        controller.state.elapsed_time = time.time() - controller._start_time

    # 获取当前Agent的ID
    current_agent_id = None
    enabled_agents = agent_manager.get_enabled()
    if controller.state.current_agent_name:
        for agent in enabled_agents:
            if agent.name == controller.state.current_agent_name:
                current_agent_id = agent.id
                break

    # 计算精确进度
    total_agents = selected_agent_count if selected_agent_count > 0 else len(enabled_agents)
    total_steps = controller.state.total_iterations * total_agents

    # 确保current_iteration不为负数
    current_iter = max(0, controller.state.current_iteration)
    current_agent_idx = max(0, controller.state.current_agent_index)

    # 正确的进度计算：(迭代-1)*代理数 + 当前代理索引 + 1
    # 如果迭代为0（初始状态），进度为0
    if current_iter <= 0:
        current_step = 0
    else:
        current_step = (current_iter - 1) * total_agents + current_agent_idx + 1

    if total_steps > 0 and current_step > 0:
        progress_percent = round((current_step / total_steps) * 100, 1)
    else:
        progress_percent = 0

    return {
        "status": processing_status,
        "current_document": current_document,
        "log": processing_log,
        "state": {
            "current_iteration": controller.state.current_iteration,
            "total_iterations": controller.state.total_iterations,
            "current_agent": controller.state.current_agent_name,
            "current_agent_id": current_agent_id,
            "current_agent_index": controller.state.current_agent_index,
            "total_agents": total_agents,
            "current_model": controller.state.current_model_name,
            "total_tokens": global_total_prompt_tokens + global_total_completion_tokens,  # 使用全局累计值
            "search_count": global_total_searches,  # 使用全局累计值
            "search_logs": controller.state.search_logs if controller else [],
            "elapsed_time": controller.state.elapsed_time,
            "is_running": controller.state.is_running,
            "current_step": current_step,
            "total_steps": total_steps,
            "progress_percent": progress_percent
        },
        "agent_results": agent_results
    }

@app.post("/api/clear", dependencies=[Depends(require_auth)])
async def clear_all():
    """清空所有内容"""
    global current_document, processing_status, processing_log, agent_results
    global global_total_prompt_tokens, global_total_completion_tokens, global_total_searches

    # 重置文档
    current_document = ""

    # 重置处理状态
    processing_status = "idle"
    app.state.processing_status = processing_status

    # 清空日志
    processing_log.clear()

    # 清空Agent执行结果
    agent_results = {}

    # 清空附件
    attachment_manager.clear()

    # 重置全局Token统计
    global_total_prompt_tokens = 0
    global_total_completion_tokens = 0
    global_total_searches = 0

    # 重置控制器状态
    if controller:
        controller.state.is_running = False
        controller.state.current_iteration = 0
        controller.state.current_agent_index = 0
        controller.state.current_agent_name = ""
        controller.state.current_model_name = ""
        controller.state.total_tokens = 0
        controller.state.search_count = 0
        controller.state.search_logs = []
        controller.state.elapsed_time = 0.0

    return {"status": "success", "message": "已清空所有内容"}

@app.post("/api/stream-process", dependencies=[Depends(require_auth)])
async def stream_process(request: ProcessRequest):
    """流式处理文档，实时返回结果"""
    from fastapi.responses import StreamingResponse
    import asyncio

    global processing_status, current_document

    processing_status = "running"
    app.state.processing_status = processing_status
    current_document = request.content

    async def generate():
        global processing_status, current_document

        try:
            has_configured_model = any(m.api_key for m in model_manager.get_all())
            if not has_configured_model:
                yield f"data: {{\"status\": \"error\", \"message\": \"请先配置至少一个模型的API密钥\"}}\n\n"
                return

            if request.agent_ids:
                selected_agents = [agent_manager.get(agent_id) for agent_id in request.agent_ids if agent_manager.get(agent_id)]
                if not selected_agents:
                    yield f"data: {{\"status\": \"error\", \"message\": \"选择的Agent不存在\"}}\n\n"
                    return
            else:
                selected_agents = agent_manager.get_enabled()
                if not selected_agents:
                    yield f"data: {{\"status\": \"error\", \"message\": \"请至少启用一个Agent\"}}\n\n"
                    return

            controller = IterationController(
                agent_manager=agent_manager,
                model_manager=model_manager,
                log_manager=log_manager,
                search_manager=search_manager if request.enable_search else None,
                iterations=request.iterations
            )

            yield f"data: {{\"status\": \"started\", \"message\": \"开始处理...\"}}\n\n"
            yield f"data: {{\"status\": \"log\", \"message\": \"已选择 {len(selected_agents)} 个Agent: {', '.join([a.name for a in selected_agents])}\"}}\n\n"

            for iteration in range(1, request.iterations + 1):
                if processing_status == "stopped":
                    yield f"data: {{\"status\": \"stopped\", \"message\": \"用户停止处理\"}}\n\n"
                    return

                yield f"data: {{\"status\": \"iteration\", \"message\": \"迭代 {iteration}/{request.iterations} 开始\"}}\n\n"

                buffer = []
                buffer_size = 0

                for event in controller.run_iteration_stream(iteration, current_document, request.agent_ids):
                    if processing_status == "stopped":
                        yield f"data: {{\"status\": \"stopped\", \"message\": \"用户停止处理\"}}\n\n"
                        return

                    if event["type"] == "agent_start":
                        yield f"data: {{\"status\": \"agent_start\", \"agent\": \"{event['agent_name']}\", \"model\": \"{event['model_name']}\"}}\n\n"

                    elif event["type"] == "chunk":
                        buffer.append(event["content"])
                        buffer_size += len(event["content"])

                        if buffer_size >= 50 or len(buffer) >= 10:
                            current_document += ''.join(buffer)
                            yield f"data: {{\"status\": \"chunk\", \"content\": {json.dumps(''.join(buffer))}}}\n\n"
                            buffer = []
                            buffer_size = 0
                            await asyncio.sleep(0.01)

                    elif event["type"] == "agent_complete":
                        if buffer:
                            current_document += ''.join(buffer)
                            yield f"data: {{\"status\": \"chunk\", \"content\": {json.dumps(''.join(buffer))}}}\n\n"
                            buffer = []
                            buffer_size = 0
                        current_document = event["content"]
                        yield f"data: {{\"status\": \"agent_complete\", \"agent\": \"{event['agent_name']}\"}}\n\n"

                    elif event["type"] == "error":
                        yield f"data: {{\"status\": \"error\", \"message\": \"{event['message']}\"}}\n\n"

                    elif event["type"] == "iteration_complete":
                        if buffer:
                            current_document += ''.join(buffer)
                            yield f"data: {{\"status\": \"chunk\", \"content\": {json.dumps(''.join(buffer))}}}\n\n"
                        current_document = event["content"]
                        break

            yield f"data: {{\"status\": \"completed\", \"content\": {json.dumps(current_document)}}}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {{\"status\": \"error\", \"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.websocket("/ws/process")
async def websocket_process(websocket: WebSocket):
    """WebSocket endpoint for streaming document processing"""
    global global_total_prompt_tokens, global_total_completion_tokens, global_total_searches
    global controller, current_document, processing_status, processing_log, agent_results
    global selected_agent_count

    # 认证：要求 session 中真实登录用户（cookie 非空不再足够）
    _sess = websocket.session if hasattr(websocket, "session") else {}
    _ws_user = _sess.get("user") or _sess.get("mu_user") if _sess else None
    if not _ws_user:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info("WebSocket connection established")
    await safe_send_json(websocket, {"status": "log", "message": "WebSocket连接已建立"})

    # 初始化统计变量（使用全局累计值）
    start_time = None
    current_iteration = 0
    total_iterations = 0
    current_agent_index = 0
    total_agents = 0

    async def send_stats():
        """发送当前统计信息到前端"""
        elapsed = (datetime.now() - start_time).total_seconds() if start_time else 0
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        # 从controller.state获取状态
        iter_state = controller.state if controller else None
        current_iter = iter_state.current_iteration if iter_state else 0
        total_iter = iter_state.total_iterations if iter_state else 0
        agent_idx = iter_state.current_agent_index if iter_state else 0

        # 计算步骤进度（使用total_agents确保正确性）
        selected_agent_count = total_agents
        total_steps = total_iter * selected_agent_count if total_iter > 0 and selected_agent_count > 0 else 0
        if current_iter > 0 and selected_agent_count > 0:
            current_step = (current_iter - 1) * selected_agent_count + agent_idx + 1
        else:
            current_step = 0

        await safe_send_json(websocket, {
            "status": "stats",
            "iteration": current_iter,
            "total_iterations": total_iter,
            "current_step": current_step,
            "total_steps": total_steps,
            "total_tokens": global_total_prompt_tokens + global_total_completion_tokens,
            "prompt_tokens": global_total_prompt_tokens,
            "completion_tokens": global_total_completion_tokens,
            "searches": global_total_searches,
            "elapsed_time": time_str
        })

    try:
        data = await websocket.receive_json()
        content = data.get("content", "")
        iterations = data.get("iterations", 1)
        enable_search = data.get("enable_search", False)
        agent_ids = data.get("agent_ids", [])
        total_iterations = iterations

        # 开始计时
        start_time = datetime.now()

        logger.info(f"Received request: iterations={iterations}, enable_search={enable_search}, content_length={len(content)}, agent_ids={agent_ids}")
        await safe_send_json(websocket, {"status": "log", "message": f"收到处理请求: 内容长度={len(content)}, 迭代次数={iterations}, 启用搜索={enable_search}"})

        has_configured_model = any(m.api_key for m in model_manager.get_all())
        if not has_configured_model:
            await safe_send_json(websocket, {"status": "error", "message": "请先配置至少一个模型的API密钥"})
            return

        if agent_ids:
            selected_agents = [agent_manager.get(agent_id) for agent_id in agent_ids if agent_manager.get(agent_id)]
            if not selected_agents:
                await safe_send_json(websocket, {"status": "error", "message": "选择的Agent不存在"})
                return
        else:
            selected_agents = agent_manager.get_enabled()
            if not selected_agents:
                await safe_send_json(websocket, {"status": "error", "message": "请至少启用一个Agent"})
                return

        # 设置Agent总数
        total_agents = len(selected_agents)
        selected_agent_count = total_agents  # 更新全局变量

        await safe_send_json(websocket, {"status": "log", "message": f"已选择 {len(selected_agents)} 个Agent: {', '.join([a.name for a in selected_agents])}"})

        # 重置全局状态
        current_document = content
        processing_status = "processing"
        app.state.processing_status = processing_status
        processing_log.clear()
        agent_results = {}

        # 创建控制器（使用全局变量）
        controller = IterationController(
            agent_manager=agent_manager,
            model_manager=model_manager,
            log_manager=log_manager,
            search_manager=search_manager if enable_search else None,
            iterations=iterations
        )
        app.state.controller = controller

        await safe_send_json(websocket, {"status": "started", "message": "开始处理..."})

        # Agent索引计数器
        agent_counter = 0

        for iteration in range(1, iterations + 1):
            # 同步更新controller.state（让状态轮询能获取实时数据）
            controller.state.current_iteration = iteration
            controller.state.total_iterations = iterations

            await safe_send_json(websocket, {"status": "log", "message": f"=== 迭代 {iteration}/{iterations} 开始 ==="})
            await safe_send_json(websocket, {"status": "iteration", "message": f"迭代 {iteration}/{iterations} 开始"})

            # 发送统计更新（在迭代开始前发送，此时current_iteration仍是上一次的值）
            await send_stats()

            buffer = []
            buffer_size = 0
            agent_counter = 0  # 重置Agent计数器

            for event in controller.run_iteration_stream(iteration, content, agent_ids):
                if event["type"] == "agent_start":
                    agent_counter += 1
                    current_agent_index = agent_counter - 1  # 更新当前Agent索引

                    # 同步更新controller.state
                    controller.state.current_agent_name = event["agent_name"]
                    controller.state.current_agent_index = current_agent_index
                    controller.state.current_model_name = event["model_name"]

                    await safe_send_json(websocket, {"status": "log", "message": f"启动Agent: {event['agent_name']} (使用模型: {event['model_name']})"})
                    await safe_send_json(websocket, {
                        "status": "agent_start",
                        "agent": event["agent_name"],
                        "model": event["model_name"],
                        "iteration": event.get("iteration", 0)
                    })

                    # 发送统计更新
                    await send_stats()

                elif event["type"] == "chunk":
                    buffer.append(event["content"])
                    buffer_size += len(event["content"])

                    if buffer_size >= 50 or len(buffer) >= 10:
                        content += ''.join(buffer)
                        await safe_send_json(websocket, {"status": "chunk", "content": ''.join(buffer)})
                        buffer = []
                        buffer_size = 0
                        # 每发送一次chunk时也发送统计更新（用于更新运行时长）
                        await send_stats()
                        await asyncio.sleep(0.01)

                elif event["type"] == "agent_complete":
                    if buffer:
                        content += ''.join(buffer)
                        await safe_send_json(websocket, {"status": "chunk", "content": ''.join(buffer)})
                        buffer = []
                        buffer_size = 0
                    content = event["content"]

                    # 构建详细的Token统计日志
                    stats = event.get("stats")
                    if stats:
                        # 累加Token统计（使用全局变量）
                        global_total_prompt_tokens += stats.get('prompt_tokens', 0)
                        global_total_completion_tokens += stats.get('completion_tokens', 0)

                        stats_msg = (f"Token统计 - 输入: {stats.get('prompt_tokens', 0)} | "
                                   f"输出: {stats.get('completion_tokens', 0)} | "
                                   f"耗时: {stats.get('duration', 0):.2f}s | "
                                   f"速度: {stats.get('tokens_per_second', 0):.1f} tokens/s")
                        await safe_send_json(websocket, {"status": "log", "message": stats_msg})

                        # 发送统计更新
                        await send_stats()

                    await safe_send_json(websocket, {"status": "log", "message": f"Agent {event['agent_name']} 完成"})
                    await safe_send_json(websocket, {"status": "agent_complete", "agent": event["agent_name"], "stats": stats})

                elif event["type"] == "error":
                    await safe_send_json(websocket, {"status": "log", "message": f"错误: {event['message']}"})
                    await safe_send_json(websocket, {"status": "error", "message": event["message"]})
                    return

                elif event["type"] == "iteration_complete":
                    if buffer:
                        content += ''.join(buffer)
                        await safe_send_json(websocket, {"status": "chunk", "content": ''.join(buffer)})
                    content = event["content"]

                    # 更新当前迭代数（在迭代完成后更新）
                    current_iteration = iteration

                    # 累加搜索次数到全局变量
                    global_total_searches += controller.state.search_count

                    await safe_send_json(websocket, {"status": "log", "message": f"=== 迭代 {iteration} 完成 ==="})

                    # 发送统计更新（此时current_iteration已更新为当前迭代数）
                    await send_stats()
                    break

            await asyncio.sleep(0.1)

        await safe_send_json(websocket, {"status": "log", "message": "所有迭代完成"})

        # 更新全局状态为完成
        processing_status = "completed"
        app.state.processing_status = processing_status
        current_document = content

        # 发送最终统计
        await send_stats()

        await safe_send_json(websocket, {"status": "completed", "content": content})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        await safe_send_json(websocket, {"status": "log", "message": "WebSocket连接已断开"})
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        processing_status = "error"
        app.state.processing_status = processing_status
        await safe_send_json(websocket, {"status": "log", "message": f"发生错误: {str(e)}"})
        await safe_send_json(websocket, {"status": "error", "message": str(e)})


@app.websocket("/ws/ai-chat")
async def websocket_ai_chat(websocket: WebSocket):
    """WebSocket endpoint for AI chat streaming"""
    # 认证：要求 session 中真实登录用户（cookie 非空不再足够）
    _sess = websocket.session if hasattr(websocket, "session") else {}
    _ws_user = _sess.get("user") or _sess.get("mu_user") if _sess else None
    if not _ws_user:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info("AI Chat WebSocket connection established")

    try:
        from ai_chat_manager import ai_chat_manager
        ai_chat_manager.add_websocket(websocket)

        await safe_send_json(websocket, {"status": "connected", "message": "WebSocket连接已建立"})

        while True:
            data = await websocket.receive_json()
            if data.get("action") == "start":
                theme = data.get("theme", "")
                success = await ai_chat_manager.start_chat(theme)
                if success:
                    await safe_send_json(websocket, {"status": "started", "theme": ai_chat_manager.current_theme})
                else:
                    await safe_send_json(websocket, {"status": "error", "message": "启动聊天失败，请确保至少添加2个角色"})
            elif data.get("action") == "stop":
                await ai_chat_manager.stop_chat()
                await safe_send_json(websocket, {"status": "stopped", "message": "聊天已停止"})
            elif data.get("action") == "get_status":
                status = ai_chat_manager.get_status()
                await safe_send_json(websocket, {"status": "status", "data": status})
            elif data.get("action") == "get_messages":
                messages = ai_chat_manager.get_messages()
                await safe_send_json(websocket, {"status": "messages", "data": messages})
            elif data.get("action") == "get_roles":
                roles = ai_chat_manager.get_roles()
                await safe_send_json(websocket, {"status": "roles", "data": roles})

    except WebSocketDisconnect:
        logger.info("AI Chat WebSocket disconnected, stopping chat if running")
        from ai_chat_manager import ai_chat_manager
        ai_chat_manager.remove_websocket(websocket)
        ai_chat_manager.is_chatting = False
        if ai_chat_manager.chat_task:
            ai_chat_manager.chat_task.cancel()
            try:
                await asyncio.wait_for(ai_chat_manager.chat_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            finally:
                ai_chat_manager.chat_task = None
    except Exception as e:
        logger.error(f"AI Chat WebSocket error: {e}")
        from ai_chat_manager import ai_chat_manager
        ai_chat_manager.remove_websocket(websocket)
        ai_chat_manager.is_chatting = False
        if ai_chat_manager.chat_task:
            ai_chat_manager.chat_task.cancel()
            try:
                await asyncio.wait_for(ai_chat_manager.chat_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            finally:
                ai_chat_manager.chat_task = None


@app.post("/api/stream-llm", dependencies=[Depends(require_auth)])
async def stream_llm(prompt: str, model_id: str = None):
    """直接流式调用大模型"""
    from fastapi.responses import StreamingResponse
    import asyncio
    from engine.agent_worker import create_llm_adapter

    async def generate():
        try:
            models = model_manager.get_all()

            if model_id:
                model = model_manager.get(model_id)
            else:
                configured_models = [m for m in models if m.api_key]
                if not configured_models:
                    yield f"data: {{\"status\": \"error\", \"message\": \"请先配置模型\"}}\n\n"
                    return
                model = configured_models[0]

            adapter = create_llm_adapter(model)
            if not adapter:
                yield f"data: {{\"status\": \"error\", \"message\": \"无法创建模型适配器\"}}\n\n"
                return

            messages = [{"role": "user", "content": prompt}]

            yield f"data: {{\"status\": \"started\", \"model\": \"{model.name}\"}}\n\n"

            for chunk in adapter.chat_stream(messages):
                yield f"data: {{\"status\": \"stream\", \"chunk\": {json.dumps(chunk)}}}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {{\"status\": \"completed\"}}\n\n"

        except Exception as e:
            yield f"data: {{\"status\": \"error\", \"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    # 统一所有日志（含 uvicorn）的时间格式：YYYY-MM-DD HH:MM:SS
    LOG_FMT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"
    LOG_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": LOG_FMT, "datefmt": LOG_DATE_FMT},
            "access": {"format": LOG_FMT, "datefmt": LOG_DATE_FMT},
        },
        "handlers": {
            "default": {"formatter": "default", "class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
            "access": {"formatter": "access", "class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }

    logger.info("Starting uvicorn server...")
    try:
        uvicorn.run(
            app=app,
            host="0.0.0.0",
            port=8888,
            log_level="info",
            access_log=True,
            log_config=LOG_CONFIG,
            timeout_keep_alive=30,
        )
        logger.info("Server exited normally")
    except Exception as e:
        logger.error(f"Server failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
