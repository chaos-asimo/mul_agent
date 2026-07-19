"""Multi-Agent Document Enhancer Web Server"""
import os
import asyncio
import sys
import json
from datetime import datetime

from utils.logger import setup_logging, logger
setup_logging()

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
from web.routes import feishu as feishu_router

logger.info("Initializing FastAPI app...")
app = FastAPI(title="Multi-Agent Document Enhancer", version="1.0")

app.add_middleware(SessionMiddleware, secret_key="mul_agent_secret_key_2026")

# 启动定时任务调度器和飞书长连接
async def startup():
    logger.info("Starting cron scheduler...")
    await lobster_claw_router.cron_scheduler.start()
    
    logger.info("Starting Feishu long connection client...")
    await feishu_router.start_feishu_ws_client()

async def shutdown():
    logger.info("Stopping cron scheduler...")
    await lobster_claw_router.cron_scheduler.stop()
    
    logger.info("Stopping Feishu long connection client...")
    feishu_router.stop_feishu_ws_client()

app.add_event_handler("startup", startup)
app.add_event_handler("shutdown", shutdown)


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
app.include_router(models_router.router, prefix="/api")
app.include_router(agents_router.router, prefix="/api")
app.include_router(search_router.router, prefix="/api")
app.include_router(skills_router.router, prefix="/api")
app.include_router(attachments_router.router, prefix="/api")
app.include_router(system_router.router, prefix="")
app.include_router(image_router.router, prefix="/api")
app.include_router(video_router.router, prefix="/api")
app.include_router(ai_chat_router.router, prefix="/api")
app.include_router(lobster_claw_router.router, prefix="")
app.include_router(feishu_router.router)

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
    template = jinja_env.get_template("login.html")
    return HTMLResponse(content=template.render())


@app.post("/api/login")
async def login(request: Request, login_data: LoginRequest):
    if login_data.username == "shineyue" and login_data.password == "shineyue@2026":
        request.session["user"] = {"username": login_data.username}
        return {"status": "success", "message": "登录成功"}
    return {"status": "error", "message": "用户名或密码错误"}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return {"status": "success", "message": "退出成功"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(get_current_user)):
    """主页面"""
    if not user:
        return RedirectResponse(url="/login")
    
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

# ============ 文档处理 API（保留在 web_server.py） ============

@app.post("/api/process")
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

@app.post("/api/stop")
async def stop_processing():
    """停止处理"""
    global processing_status
    processing_status = "stopped"
    app.state.processing_status = processing_status
    controller.stop()
    return {"status": "success", "message": "已停止处理"}

@app.get("/api/status")
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

@app.post("/api/clear")
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

@app.post("/api/stream-process")
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

    session_cookie = websocket.cookies.get("session")
    if not session_cookie:
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
    session_cookie = websocket.cookies.get("session")
    if not session_cookie:
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


@app.post("/api/stream-llm")
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
    logger.info("Starting uvicorn server...")
    try:
        # 使用更稳定的配置
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8888,
            log_level="info",
            access_log=True,
            timeout_keep_alive=30
        )
        server = uvicorn.Server(config)
        server.run()
        logger.info("Server exited normally")
    except Exception as e:
        logger.error(f"Server failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
