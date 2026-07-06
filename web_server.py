"""Multi-Agent Document Enhancer Web Server"""
import os
import asyncio
import sys
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from typing import List, Optional, Dict
from models.model_config import ModelConfig
from agents.agent_config import AgentConfig
from agents.agent_manager import AgentManager
from models.model_manager import ModelManager
from attachment.attachment_manager import AttachmentManager
from engine.iteration_controller import IterationController
from llm.adapter_base import LLMResponse
from engine.agent_worker import create_llm_adapter
from search.search_manager import SearchManager
from search.search_config import SearchEngineConfig
from applogging.log_manager import LogManager
from skills.skill_manager import SkillManager
from skills.skill_executor import SkillExecutor
from skills.skill_config import SkillConfig, SkillParameter

logger.info("Initializing FastAPI app...")
app = FastAPI(title="Multi-Agent Document Enhancer", version="1.0")

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

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_config():
    return {}  # 返回空对象，消除Chrome DevTools的404请求

# 初始化控制器
controller = IterationController(
    agent_manager=agent_manager,
    model_manager=model_manager,
    log_manager=log_manager,
    search_manager=search_manager if settings["enable_search"] else None,
    iterations=settings["iterations"]
)

logger.info("App initialized successfully")

class ModelConfigItem(BaseModel):
    id: Optional[str] = None
    name: str
    api_type: str
    model_type: str = "text"
    api_url: str
    api_key: str
    model_name: str
    enabled: bool

class AgentConfigItem(BaseModel):
    id: Optional[str] = None
    name: str
    role_description: str
    model_id: str
    enabled: bool
    order: int = 0

class SearchEngineConfigItem(BaseModel):
    id: Optional[str] = None
    name: str
    adapter_type: str
    api_key: str
    api_url: str
    enabled: bool

class ProcessRequest(BaseModel):
    content: str
    iterations: int = 10
    enable_search: bool = True
    agent_ids: List[str] = []

class SettingsUpdate(BaseModel):
    iterations: int
    enable_search: bool
    max_search_per_iter: int
    default_log_level: str

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页面"""
    models = [m.to_dict() for m in model_manager.get_all()]
    agents = sorted([a.to_dict() for a in agent_manager.get_all()], key=lambda x: x['order'])
    search_engines = [s.to_dict() for s in search_manager.get_all()]
    template = jinja_env.get_template("index.html")
    html_content = template.render({
        "request": request,
        "models": models,
        "agents": agents,
        "search_engines": search_engines,
        "current_document": current_document,
        "processing_status": processing_status,
        "settings": settings,
        "logs": processing_log
    })
    return HTMLResponse(content=html_content, status_code=200)

# ============ 模型配置 API ============

@app.get("/api/models")
async def get_models():
    """获取所有模型配置"""
    return [m.to_dict() for m in model_manager.get_all()]

@app.post("/api/models")
async def create_model(config: ModelConfigItem):
    """创建新模型"""
    try:
        model = ModelConfig(
            name=config.name,
            api_type=config.api_type,
            model_type=config.model_type,
            api_url=config.api_url,
            api_key=config.api_key,
            model_name=config.model_name,
            enabled=config.enabled
        )
        model_manager.add(model)
        return {"status": "success", "message": "模型创建成功"}
    except Exception as e:
        logger.error(f"Error creating model: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"创建失败: {str(e)}"}

@app.put("/api/models/{model_id}")
async def update_model(model_id: str, config: ModelConfigItem):
    """更新模型配置"""
    model = ModelConfig(
        id=model_id,
        name=config.name,
        api_type=config.api_type,
        model_type=config.model_type,
        api_url=config.api_url,
        api_key=config.api_key,
        model_name=config.model_name,
        enabled=config.enabled
    )
    model_manager.update(model)
    return {"status": "success", "message": "模型更新成功"}

@app.delete("/api/models/{model_id}")
async def delete_model(model_id: str):
    """删除模型"""
    model_manager.delete(model_id)
    return {"status": "success", "message": "模型删除成功"}

@app.post("/api/models/{model_id}/test")
async def test_model(model_id: str):
    """测试模型连通性"""
    model = model_manager.get(model_id)
    if not model:
        return {"status": "error", "message": "模型不存在"}
    
    try:
        if model.model_type == "image":
            from engine.agent_worker import create_image_adapter
            adapter = create_image_adapter(model)
            if not adapter:
                return {"status": "error", "message": "无法创建文生图适配器"}
            
            test_prompt = "A beautiful landscape with mountains and river, digital art style"
            response = adapter.generate(test_prompt, n=1, size="256x256")
            
            if response.success:
                return {"status": "success", "message": "连接成功", "image_url": response.image_url}
            else:
                return {"status": "error", "message": f"测试失败: {response.error}"}
        else:
            adapter = create_llm_adapter(model)
            if not adapter:
                return {"status": "error", "message": "无法创建适配器"}
            
            test_messages = [{"role": "user", "content": "Hi, please respond with 'OK' if you can read this."}]
            response = adapter.chat(test_messages, max_tokens=10)
            
            if response.content and "OK" in response.content:
                return {"status": "success", "message": "连接成功"}
            else:
                return {"status": "error", "message": f"响应异常: {response.content}"}
    except Exception as e:
        return {"status": "error", "message": f"连接失败: {str(e)}"}

# ============ Agent配置 API ============

@app.get("/api/agents")
async def get_agents():
    """获取所有Agent配置"""
    return [a.to_dict() for a in agent_manager.get_all()]

@app.post("/api/agents")
async def create_agent(config: AgentConfigItem):
    """创建新Agent"""
    agent = AgentConfig(
        name=config.name,
        role_description=config.role_description,
        model_id=config.model_id,
        enabled=config.enabled,
        order=config.order
    )
    agent_manager.add(agent)
    return {"status": "success", "message": "Agent创建成功"}

@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, config: AgentConfigItem):
    """更新Agent配置"""
    agent = AgentConfig(
        id=agent_id,
        name=config.name,
        role_description=config.role_description,
        model_id=config.model_id,
        enabled=config.enabled,
        order=config.order
    )
    agent_manager.update(agent)
    return {"status": "success", "message": "Agent更新成功"}

@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除Agent"""
    agent_manager.delete(agent_id)
    return {"status": "success", "message": "Agent删除成功"}

# ============ 搜索引擎配置 API ============

@app.get("/api/search_engines")
async def get_search_engines():
    """获取所有搜索引擎配置"""
    return [s.to_dict() for s in search_manager.get_all()]

@app.post("/api/search_engines")
async def create_search_engine(config: SearchEngineConfigItem):
    """创建新搜索引擎"""
    engine = SearchEngineConfig(
        name=config.name,
        adapter_type=config.adapter_type,
        api_key=config.api_key,
        api_url=config.api_url,
        enabled=config.enabled
    )
    search_manager.add(engine)
    return {"status": "success", "message": "搜索引擎创建成功"}

@app.put("/api/search_engines/{engine_id}")
async def update_search_engine(engine_id: str, config: SearchEngineConfigItem):
    """更新搜索引擎配置"""
    engine = SearchEngineConfig(
        id=engine_id,
        name=config.name,
        adapter_type=config.adapter_type,
        api_key=config.api_key,
        api_url=config.api_url,
        enabled=config.enabled
    )
    search_manager.update(engine)
    return {"status": "success", "message": "搜索引擎更新成功"}

@app.delete("/api/search_engines/{engine_id}")
async def delete_search_engine(engine_id: str):
    """删除搜索引擎"""
    search_manager.delete(engine_id)
    return {"status": "success", "message": "搜索引擎删除成功"}

@app.post("/api/search_test")
async def test_search(query: str = Form(...)):
    """测试搜索功能"""
    if not query.strip():
        return {"status": "error", "message": "请输入搜索关键词"}
    
    try:
        results = await search_manager.search(query, num_results=3)
        if results:
            search_results = []
            for i, result in enumerate(results):
                search_results.append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
                })
            return {"status": "success", "message": "搜索成功", "results": search_results}
        else:
            return {"status": "warning", "message": "未找到搜索结果", "results": []}
    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}

@app.post("/api/search/quick")
async def quick_search(request: dict):
    """
    快速搜索API - 随时按需调用
    
    Request body:
        query: 搜索关键词
        num_results: 返回数量（默认5条）
    """
    from search.search_tool import quick_search
    
    query = request.get("query", "")
    num_results = request.get("num_results", 5)
    
    if not query.strip():
        return {"status": "error", "message": "请输入搜索关键词"}
    
    try:
        # 从搜索引擎配置中获取Tavily的API密钥
        tavily_key = ""
        for engine in search_manager.get_all():
            if engine.adapter_type == "tavily" and engine.enabled and engine.api_key:
                tavily_key = engine.api_key
                break
        
        if not tavily_key:
            return {"status": "warning", "message": "未配置Tavily搜索，请先在设置中添加搜索引擎", "results": []}
        
        # 执行搜索
        results = await quick_search(query, tavily_key, num_results)
        
        return {
            "status": "success",
            "message": f"搜索成功，获取到 {len(results)} 条结果",
            "results": results
        }
    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}

@app.post("/api/search/context")
async def search_for_context(request: dict):
    """
    搜索并返回格式化上下文 - 随时按需调用
    
    Request body:
        query: 搜索关键词
        num_results: 返回数量（默认3条）
    """
    from search.search_tool import quick_search_context
    
    query = request.get("query", "")
    num_results = request.get("num_results", 3)
    
    if not query.strip():
        return {"status": "error", "message": "请输入搜索关键词"}
    
    try:
        # 从搜索引擎配置中获取Tavily的API密钥
        tavily_key = ""
        for engine in search_manager.get_all():
            if engine.adapter_type == "tavily" and engine.enabled and engine.api_key:
                tavily_key = engine.api_key
                break
        
        if not tavily_key:
            return {"status": "warning", "message": "未配置Tavily搜索", "context": ""}
        
        # 执行搜索并返回格式化上下文
        context = await quick_search_context(query, tavily_key, num_results)
        
        return {
            "status": "success",
            "message": "搜索完成",
            "context": context
        }
    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}

# ============ Skill管理 API ============

@app.get("/api/skills")
async def get_skills():
    """获取所有Skills"""
    skills = skill_manager.get_all()
    return {"skills": [s.to_dict() for s in skills]}

@app.get("/api/skills/{skill_id}")
async def get_skill(skill_id: str):
    """获取单个Skill"""
    skill = skill_manager.get_by_id(skill_id)
    if skill:
        return {"skill": skill.to_dict()}
    return {"error": "Skill不存在"}

@app.post("/api/skills")
async def create_skill(skill_data: dict):
    """创建新Skill"""
    skill = SkillConfig.from_dict(skill_data)
    
    # 验证Skill配置
    errors = skill_manager.validate_skill(skill)
    if errors:
        return {"status": "error", "message": "配置验证失败", "errors": errors}
    
    if skill_manager.add(skill):
        return {"status": "success", "message": "Skill创建成功", "skill": skill.to_dict()}
    return {"status": "error", "message": "Skill已存在"}

@app.put("/api/skills/{skill_id}")
async def update_skill(skill_id: str, skill_data: dict):
    """更新Skill"""
    skill = SkillConfig.from_dict(skill_data)
    skill.id = skill_id
    
    # 验证Skill配置
    errors = skill_manager.validate_skill(skill)
    if errors:
        return {"status": "error", "message": "配置验证失败", "errors": errors}
    
    if skill_manager.update(skill):
        return {"status": "success", "message": "Skill更新成功", "skill": skill.to_dict()}
    return {"status": "error", "message": "Skill不存在"}

@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """删除Skill"""
    if skill_manager.delete(skill_id):
        return {"status": "success", "message": "Skill删除成功"}
    return {"status": "error", "message": "Skill不存在"}

@app.post("/api/skills/{skill_id}/enable")
async def enable_skill(skill_id: str):
    """启用Skill"""
    if skill_manager.enable(skill_id):
        return {"status": "success", "message": "Skill已启用"}
    return {"status": "error", "message": "Skill不存在"}

@app.post("/api/skills/{skill_id}/disable")
async def disable_skill(skill_id: str):
    """禁用Skill"""
    if skill_manager.disable(skill_id):
        return {"status": "success", "message": "Skill已禁用"}
    return {"status": "error", "message": "Skill不存在"}

@app.post("/api/skills/analyze")
async def analyze_skills(request: dict):
    """分析输入内容，返回建议调用的Skills"""
    content = request.get("content", "")

    if not content:
        return {"status": "success", "matched_skills": [], "reason": "输入内容为空"}

    # 获取所有启用的Skills
    enabled_skills = [s for s in skill_manager.get_all() if s.enabled]

    if not enabled_skills:
        return {"status": "success", "matched_skills": [], "reason": "没有启用的Skills"}

    matched = []

    for skill in enabled_skills:
        score = 0
        reasons = []

        # 检查名称关键词
        name_keywords = skill.name.lower().split()
        content_lower = content.lower()
        for keyword in name_keywords:
            if keyword in content_lower:
                score += 2
                reasons.append(f"名称匹配: {keyword}")

        # 检查描述关键词
        if skill.description:
            desc_keywords = skill.description.lower().split()
            for keyword in desc_keywords:
                if len(keyword) > 2 and keyword in content_lower:
                    score += 1
                    reasons.append(f"描述匹配: {keyword}")

        # 检查标签
        if skill.tags:
            for tag in skill.tags:
                if tag.lower() in content_lower:
                    score += 1.5
                    reasons.append(f"标签匹配: {tag}")

        # 检查类型关键词
        type_keywords = {
            "search": ["搜索", "查找", "查询", "search", "find"],
            "analysis": ["分析", "研究", "研究", "analysis", "analyze"],
            "generation": ["生成", "创建", "编写", "生成", "generate", "create"],
            "transform": ["转换", "翻译", "改写", "transform", "translate"],
            "validation": ["验证", "检查", "测试", "validate", "check", "verify"]
        }

        skill_type_value = skill.skill_type.value if hasattr(skill.skill_type, 'value') else str(skill.skill_type)
        if skill_type_value in type_keywords:
            for keyword in type_keywords[skill_type_value]:
                if keyword in content_lower:
                    score += 1
                    reasons.append(f"类型匹配: {keyword}")

        if score > 0:
            matched.append({
                "skill_id": skill.id,
                "skill_name": skill.name,
                "score": score,
                "reasons": reasons
            })

    # 按分数排序
    matched.sort(key=lambda x: x["score"], reverse=True)

    # 取分数最高的3个
    top_matches = matched[:3]

    return {
        "status": "success",
        "matched_skills": top_matches,
        "reason": f"找到 {len(top_matches)} 个可能的Skill"
    }


@app.post("/api/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, request: dict):
    """执行Skill"""
    params = request.get("params", {})
    context = request.get("context", {})
    
    print(f"[API] execute_skill: skill_id={skill_id}, params={params}")
    print(f"[API] skill_executor.search_manager={skill_executor.search_manager}")
    print(f"[API] adapters={skill_executor.search_manager.adapters if skill_executor.search_manager else None}")

    result = await skill_executor.execute(skill_id, params, context)
    return {"result": result.to_dict()}

@app.post("/api/skills/chain")
async def execute_skill_chain(request: dict):
    """执行Skill链"""
    skill_ids = request.get("skill_ids", [])
    params = request.get("params", {})
    
    results = await skill_executor.execute_chain(skill_ids, params)
    return {"results": [r.to_dict() for r in results]}

@app.get("/api/skills/history")
async def get_skill_history(limit: int = 50):
    """获取Skill执行历史"""
    history = skill_executor.get_execution_history(limit)
    return {"history": history}

@app.post("/api/skills/reset")
async def reset_skills():
    """重置Skills为默认配置"""
    skill_manager.reset_to_default()
    return {"status": "success", "message": "Skills已重置为默认配置"}

# ============ 附件管理 API ============

@app.post("/api/attachments/upload")
async def upload_attachment(file: UploadFile = File(...)):
    """上传附件"""
    try:
        # 创建上传目录
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        # 保存文件
        filepath = os.path.join(upload_dir, file.filename)
        content = await file.read()
        with open(filepath, 'wb') as f:
            f.write(content)
        
        # 添加到附件管理器
        attachment_manager.add_attachment(filepath)
        return {"status": "success", "message": "附件上传成功", "filename": file.filename}
    except Exception as e:
        return {"status": "error", "message": f"上传失败: {str(e)}"}

@app.get("/api/attachments")
async def get_attachments():
    """获取所有附件"""
    attachments = attachment_manager.get_attachments()
    return [att.filename for att in attachments]

@app.delete("/api/attachments/{filename}")
async def delete_attachment(filename: str):
    """删除附件"""
    # 根据文件名找到附件并删除
    attachments = attachment_manager.get_attachments()
    for att in attachments:
        if att.filename == filename:
            attachment_manager.remove_attachment(att.id)
            return {"status": "success", "message": "附件删除成功"}
    return {"status": "error", "message": "附件不存在"}

@app.post("/api/attachments/clear")
async def clear_attachments():
    """清空所有附件"""
    attachment_manager.clear()
    return {"status": "success", "message": "已清空所有附件"}

# ============ 文档处理 API ============

@app.post("/api/process")
async def process_document(request: ProcessRequest):
    """处理文档"""
    global current_document, processing_status, processing_log, controller
    
    current_document = request.content
    processing_status = "processing"
    processing_log = []
    
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
    controller.stop()
    return {"status": "success", "message": "已停止处理"}

@app.get("/api/version")
async def get_version_api():
    """获取应用版本号"""
    return {"version": app_version}

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
    
    # 清空日志
    processing_log = []
    
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

# ============ 设置 API ============

@app.get("/api/settings")
async def get_settings():
    """获取当前设置"""
    return settings

@app.put("/api/settings")
async def update_settings(new_settings: SettingsUpdate):
    """更新设置"""
    global settings, controller
    
    settings["iterations"] = new_settings.iterations
    settings["enable_search"] = new_settings.enable_search
    settings["max_search_per_iter"] = new_settings.max_search_per_iter
    settings["default_log_level"] = new_settings.default_log_level
    
    # 更新控制器
    controller = IterationController(
        agent_manager=agent_manager,
        model_manager=model_manager,
        log_manager=log_manager,
        search_manager=search_manager if settings["enable_search"] else None,
        iterations=settings["iterations"]
    )
    
    return {"status": "success", "message": "设置更新成功"}

# ============ 日志管理 API ============

@app.get("/api/logs")
async def get_logs():
    """获取处理日志"""
    return {"logs": processing_log}

@app.post("/api/stream-process")
async def stream_process(request: ProcessRequest):
    """流式处理文档，实时返回结果"""
    from fastapi.responses import StreamingResponse
    import asyncio
    
    global processing_status, current_document
    
    processing_status = "running"
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
    
    await websocket.accept()
    logger.info("WebSocket connection established")
    await websocket.send_json({"status": "log", "message": "WebSocket连接已建立"})
    
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
        
        await websocket.send_json({
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
        await websocket.send_json({"status": "log", "message": f"收到处理请求: 内容长度={len(content)}, 迭代次数={iterations}, 启用搜索={enable_search}"})
        
        has_configured_model = any(m.api_key for m in model_manager.get_all())
        if not has_configured_model:
            await websocket.send_json({"status": "error", "message": "请先配置至少一个模型的API密钥"})
            return
        
        if agent_ids:
            selected_agents = [agent_manager.get(agent_id) for agent_id in agent_ids if agent_manager.get(agent_id)]
            if not selected_agents:
                await websocket.send_json({"status": "error", "message": "选择的Agent不存在"})
                return
        else:
            selected_agents = agent_manager.get_enabled()
            if not selected_agents:
                await websocket.send_json({"status": "error", "message": "请至少启用一个Agent"})
                return
        
        # 设置Agent总数
        total_agents = len(selected_agents)
        selected_agent_count = total_agents  # 更新全局变量
        
        await websocket.send_json({"status": "log", "message": f"已选择 {len(selected_agents)} 个Agent: {', '.join([a.name for a in selected_agents])}"})
        
        # 重置全局状态
        current_document = content
        processing_status = "processing"
        processing_log = []
        agent_results = {}
        
        # 创建控制器（使用全局变量）
        controller = IterationController(
            agent_manager=agent_manager,
            model_manager=model_manager,
            log_manager=log_manager,
            search_manager=search_manager if enable_search else None,
            iterations=iterations
        )
        
        await websocket.send_json({"status": "started", "message": "开始处理..."})
        
        # Agent索引计数器
        agent_counter = 0
        
        for iteration in range(1, iterations + 1):
            # 同步更新controller.state（让状态轮询能获取实时数据）
            controller.state.current_iteration = iteration
            controller.state.total_iterations = iterations
            
            await websocket.send_json({"status": "log", "message": f"=== 迭代 {iteration}/{iterations} 开始 ==="})
            await websocket.send_json({"status": "iteration", "message": f"迭代 {iteration}/{iterations} 开始"})
            
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
                    
                    await websocket.send_json({"status": "log", "message": f"启动Agent: {event['agent_name']} (使用模型: {event['model_name']})"})
                    await websocket.send_json({
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
                        await websocket.send_json({"status": "chunk", "content": ''.join(buffer)})
                        buffer = []
                        buffer_size = 0
                        # 每发送一次chunk时也发送统计更新（用于更新运行时长）
                        await send_stats()
                        await asyncio.sleep(0.01)
                
                elif event["type"] == "agent_complete":
                    if buffer:
                        content += ''.join(buffer)
                        await websocket.send_json({"status": "chunk", "content": ''.join(buffer)})
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
                        await websocket.send_json({"status": "log", "message": stats_msg})
                        
                        # 发送统计更新
                        await send_stats()
                    
                    await websocket.send_json({"status": "log", "message": f"Agent {event['agent_name']} 完成"})
                    await websocket.send_json({"status": "agent_complete", "agent": event["agent_name"], "stats": stats})
                
                elif event["type"] == "error":
                    await websocket.send_json({"status": "log", "message": f"错误: {event['message']}"})
                    await websocket.send_json({"status": "error", "message": event["message"]})
                    return
                
                elif event["type"] == "iteration_complete":
                    if buffer:
                        content += ''.join(buffer)
                        await websocket.send_json({"status": "chunk", "content": ''.join(buffer)})
                    content = event["content"]
                    
                    # 更新当前迭代数（在迭代完成后更新）
                    current_iteration = iteration
                    
                    # 累加搜索次数到全局变量
                    global_total_searches += controller.state.search_count
                    
                    await websocket.send_json({"status": "log", "message": f"=== 迭代 {iteration} 完成 ==="})
                    
                    # 发送统计更新（此时current_iteration已更新为当前迭代数）
                    await send_stats()
                    break
            
            await asyncio.sleep(0.1)
        
        await websocket.send_json({"status": "log", "message": "所有迭代完成"})
        
        # 更新全局状态为完成
        processing_status = "completed"
        current_document = content
        
        # 发送最终统计
        await send_stats()
        
        await websocket.send_json({"status": "completed", "content": content})
        
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        await websocket.send_json({"status": "log", "message": "WebSocket连接已断开"})
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({"status": "log", "message": f"发生错误: {str(e)}"})
        await websocket.send_json({"status": "error", "message": str(e)})


@app.websocket("/ws/ai-chat")
async def websocket_ai_chat(websocket: WebSocket):
    """WebSocket endpoint for AI chat streaming"""
    await websocket.accept()
    logger.info("AI Chat WebSocket connection established")
    
    try:
        from ai_chat_manager import ai_chat_manager
        ai_chat_manager.add_websocket(websocket)
        
        await websocket.send_json({"status": "connected", "message": "WebSocket连接已建立"})
        
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "start":
                theme = data.get("theme", "")
                success = await ai_chat_manager.start_chat(theme)
                if success:
                    await websocket.send_json({"status": "started", "theme": ai_chat_manager.current_theme})
                else:
                    await websocket.send_json({"status": "error", "message": "启动聊天失败，请确保至少添加2个角色"})
            elif data.get("action") == "stop":
                await ai_chat_manager.stop_chat()
                await websocket.send_json({"status": "stopped", "message": "聊天已停止"})
            elif data.get("action") == "get_status":
                status = ai_chat_manager.get_status()
                await websocket.send_json({"status": "status", "data": status})
            elif data.get("action") == "get_messages":
                messages = ai_chat_manager.get_messages()
                await websocket.send_json({"status": "messages", "data": messages})
            elif data.get("action") == "get_roles":
                roles = ai_chat_manager.get_roles()
                await websocket.send_json({"status": "roles", "data": roles})
    
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
                if ai_chat_manager.messages:
                    ai_chat_manager.save_current_chat()
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
                if ai_chat_manager.messages:
                    ai_chat_manager.save_current_chat()


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

# ============ 文生图 API ============

class ImageGenerateRequest(BaseModel):
    prompt: str
    model_id: Optional[str] = None
    n: int = 1
    size: str = "1024x1024"
    negative_prompt: str = ""

@app.post("/api/image-generate")
async def generate_image(request: ImageGenerateRequest):
    """文生图API"""
    try:
        models = model_manager.get_all()
        
        if request.model_id:
            model = model_manager.get(request.model_id)
        else:
            image_models = [m for m in models if m.api_key and m.enabled and m.model_type == "image"]
            if not image_models:
                return {"status": "error", "message": "请先配置至少一个文生图模型"}
            model = image_models[0]
        
        if model.model_type != "image":
            return {"status": "error", "message": "选择的模型不是文生图模型"}
        
        from engine.agent_worker import create_image_adapter
        adapter = create_image_adapter(model)
        if not adapter:
            return {"status": "error", "message": "无法创建文生图适配器"}
        
        response = adapter.generate(
            prompt=request.prompt,
            n=request.n,
            size=request.size,
            negative_prompt=request.negative_prompt
        )
        
        if response.success:
            return {
                "status": "success",
                "model": model.name,
                "image_url": response.image_url,
                "image_data": response.image_data.decode('utf-8') if response.image_data else None
            }
        else:
            return {"status": "error", "message": f"生成失败: {response.error}"}
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"生成失败: {str(e)}"}

@app.get("/api/image-models")
async def get_image_models():
    """获取所有文生图模型"""
    image_models = [m.to_dict() for m in model_manager.get_all() if m.model_type == "image"]
    return image_models

# ============ 文生视频 API ============

class VideoGenerateRequest(BaseModel):
    prompt: str
    model_id: Optional[str] = None
    width: int = 1152
    height: int = 768
    num_frames: int = 121
    frame_rate: int = 24
    image_url: Optional[str] = None
    negative_prompt: str = ""

# 任务状态存储
video_tasks = {}

@app.post("/api/video-generate")
async def generate_video(request: VideoGenerateRequest):
    """文生视频API"""
    try:
        models = model_manager.get_all()
        
        if request.model_id:
            model = model_manager.get(request.model_id)
        else:
            video_models = [m for m in models if m.api_key and m.enabled and m.model_type == "video"]
            if not video_models:
                return {"status": "error", "message": "请先配置至少一个文生视频模型"}
            model = video_models[0]
        
        if model.model_type != "video":
            return {"status": "error", "message": "选择的模型不是文生视频模型"}
        
        from engine.agent_worker import create_video_adapter
        adapter = create_video_adapter(model)
        if not adapter:
            return {"status": "error", "message": "无法创建视频适配器"}
        
        # 生成任务
        video_data = {
            "model": model.model_name,
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "num_frames": request.num_frames,
            "frame_rate": request.frame_rate
        }
        
        if request.image_url:
            video_data["image"] = request.image_url
        
        if request.negative_prompt:
            video_data["negative_prompt"] = request.negative_prompt
        
        # 创建任务并获取task_id
        response = adapter.generate(**video_data)
        
        if response.success and hasattr(response, 'video_id'):
            # 保存任务状态
            video_tasks[response.video_id] = {
                "status": response.status,
                "progress": response.progress,
                "model": model.name,
                "model_id": model.id,
                "created_at": int(__import__('time').time())
            }
            
            return {
                "status": "success",
                "video_id": response.video_id,
                "task_id": response.task_id,
                "message": "视频生成任务已创建，请轮询状态"
            }
        elif response.success and hasattr(response, 'task_id'):
            video_tasks[response.task_id] = {
                "status": response.status,
                "progress": response.progress,
                "model": model.name,
                "model_id": model.id,
                "created_at": int(__import__('time').time())
            }
            
            return {
                "status": "success",
                "video_id": getattr(response, 'video_id', response.task_id),
                "task_id": response.task_id,
                "message": "视频生成任务已创建，请轮询状态"
            }
        else:
            return {"status": "error", "message": f"创建任务失败: {response.error}"}
            
    except Exception as e:
        logger.error(f"Video generation error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"创建任务失败: {str(e)}"}

@app.get("/api/video-status/{video_id}")
async def get_video_status(video_id: str):
    """获取视频生成状态"""
    try:
        logger.info(f"视频状态查询请求: video_id={video_id}")
        
        import time
        now = int(time.time())
        
        # 从video_tasks获取创建任务时使用的模型ID
        task = video_tasks.get(video_id)
        
        if task and task.get("model_id"):
            # 使用创建任务时相同的模型
            model_id = task["model_id"]
            models = model_manager.get_all()
            model = next((m for m in models if m.id == model_id), None)
        else:
            # 如果没有找到任务记录，回退到使用第一个视频模型
            models = model_manager.get_all()
            video_models = [m for m in models if m.api_key and m.enabled and m.model_type == "video"]
            if not video_models:
                return {"code": "error", "message": "没有可用的视频模型"}
            model = video_models[0]
        
        if not model:
            return {"code": "error", "message": f"找不到模型ID: {model_id}"}
        from engine.agent_worker import create_video_adapter
        adapter = create_video_adapter(model)
        if not adapter:
            return {"code": "error", "message": "无法创建视频适配器"}
        
        task_info = adapter.get_status(video_id)
        logger.info(f"适配器返回的任务信息: {task_info}")
        
        if task_info:
            # 更新本地缓存
            if video_id in video_tasks:
                # 如果已有缓存，保留额外信息
                video_tasks[video_id].update({
                    "status": task_info.get("status", "unknown"),
                    "progress": task_info.get("progress", 0),
                    "video_url": task_info.get("video_url", ""),
                    "error": task_info.get("error"),
                    "seconds": task_info.get("seconds"),
                    "size": task_info.get("size")
                })
            else:
                video_tasks[video_id] = {
                    "status": task_info.get("status", "unknown"),
                    "progress": task_info.get("progress", 0),
                    "video_url": task_info.get("video_url", ""),
                    "error": task_info.get("error"),
                    "seconds": task_info.get("seconds"),
                    "size": task_info.get("size")
                }
            
            # 构建返回数据
            result = {
                "code": "success",
                "video_id": video_id,
                "task_status": task_info.get("status", "unknown"),
                "progress": task_info.get("progress", 0),
                "video_url": task_info.get("video_url", ""),
                "error": task_info.get("error"),
                "seconds": task_info.get("seconds"),
                "size": task_info.get("size")
            }
            
            # 如果视频已完成且有URL，添加视频信息
            if task_info.get("status") == "completed" and task_info.get("video_url"):
                # 尝试获取视频文件大小
                try:
                    video_path = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)),
                        "uploads", "videos",
                        task_info["video_url"].lstrip("/uploads/videos/")
                    )
                    if os.path.exists(video_path):
                        size_bytes = os.path.getsize(video_path)
                        result["size"] = f"{size_bytes / (1024*1024):.1f}MB"
                        result["seconds"] = task_info.get("seconds", "未知")
                except:
                    pass
            
            return result
        else:
            return {"code": "error", "message": "无法获取视频状态"}
            
    except Exception as e:
        logger.error(f"Video status error: {e}")
        return {"code": "error", "message": f"获取状态失败: {str(e)}"}

@app.get("/api/video-models")
async def get_video_models():
    """获取所有文生视频模型"""
    video_models = [m.to_dict() for m in model_manager.get_all() if m.model_type == "video"]
    return video_models

# ============ 视频提示词优化 API ============

@app.post("/api/optimize-prompt")
async def optimize_prompt(request: Request):
    """随机选择一个文本模型优化视频提示词"""
    import random
    from engine.agent_worker import create_llm_adapter
    
    try:
        # 获取请求体
        body = await request.json()
        prompt = body.get("prompt", "")
        
        if not prompt:
            return {"code": "error", "message": "提示词不能为空"}
        
        # 获取所有可用的文本模型
        models = model_manager.get_all()
        text_models = [m for m in models if m.api_key and m.enabled and m.model_type == "text"]
        
        if not text_models:
            return {"code": "error", "message": "没有可用的文本模型"}
        
        # 随机选择一个模型
        selected_model = random.choice(text_models)
        logger.info(f"选择模型优化提示词: {selected_model.name} ({selected_model.model_name})")
        
        # 创建适配器
        adapter = create_llm_adapter(selected_model)
        if not adapter:
            return {"code": "error", "message": f"无法为模型 {selected_model.name} 创建适配器"}
        
        # 构建优化提示词
        system_prompt = """你是一个专业的视频提示词优化专家。请帮助用户优化他们的视频生成提示词，使其更加详细、精美和生动。

优化要求：
1. 保持原始意图和主题
2. 添加丰富的视觉细节描述（光线、色彩、氛围、运动等）
3. 使用更具表现力的语言
4. 保持提示词简洁但有画面感
5. 如果原始提示词很简单，适当扩展但不要过度

请直接返回优化后的提示词，不要添加额外的解释或说明。"""

        # 调用模型优化提示词
        response = adapter.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请优化这个视频提示词：{prompt}"}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        # 获取优化的提示词
        optimized_prompt = response.content.strip()
        
        return {
            "code": "success",
            "original_prompt": prompt,
            "optimized_prompt": optimized_prompt,
            "model_used": f"{selected_model.name} ({selected_model.model_name})"
        }
        
    except Exception as e:
        logger.error(f"提示词优化失败: {e}")
        return {"code": "error", "message": f"优化失败: {str(e)}"}

# ============ 模型调用日志 API ============

@app.get("/api/model_calls")
async def get_model_calls(limit: int = 20):
    """获取模型调用日志"""
    from llm.model_call_logger import model_call_logger
    logs = model_call_logger.get_logs(limit)
    return {"logs": logs}

@app.get("/api/model_calls/{log_id}")
async def get_model_call(log_id: str):
    """获取单个模型调用日志详情"""
    from llm.model_call_logger import model_call_logger
    log = model_call_logger.get_log_by_id(log_id)
    if log:
        return {"log": log}
    return {"status": "error", "message": "日志不存在"}

@app.delete("/api/model_calls")
async def clear_model_calls():
    """清空模型调用日志"""
    from llm.model_call_logger import model_call_logger
    model_call_logger.clear_logs()
    return {"status": "success", "message": "模型调用日志已清空"}

@app.post("/api/logs/export")
async def export_logs():
    """导出日志到浏览器下载"""
    if not processing_log:
        return {"status": "error", "message": "没有日志可导出"}
    
    try:
        from fastapi.responses import PlainTextResponse
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs_export_{timestamp}.txt"
        content = "\n".join(processing_log)
        
        headers = {
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Content-Type": "text/plain; charset=utf-8"
        }
        
        return PlainTextResponse(content, headers=headers)
    except Exception as e:
        return {"status": "error", "message": f"导出失败: {str(e)}"}

@app.post("/api/logs/clear")
async def clear_logs():
    """清空日志"""
    global processing_log
    processing_log = []
    return {"status": "success", "message": "日志已清空"}

# ============ 文档保存 API ============

@app.post("/api/save")
async def save_document(content: str = Form(...), filename: str = Form(...)):
    """保存文档"""
    try:
        if not filename.endswith('.md'):
            filename += '.md'
        filepath = os.path.join('dist/logs/outputs', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"status": "success", "message": f"文档已保存为 {filename}"}
    except Exception as e:
        return {"status": "error", "message": f"保存失败: {str(e)}"}

# ============ 系统信息 API ============

@app.get("/api/system_info")
async def get_system_info():
    """获取系统信息"""
    return {
        "models_count": len(model_manager.get_all()),
        "agents_count": len(agent_manager.get_all()),
        "search_engines_count": len(search_manager.get_all()),
        "attachments_count": len(attachment_manager.get_attachments()),
        "processing_status": processing_status
    }

# ============ 周易卜卦 API ============

@app.get("/api/yijing/shake")
async def yijing_shake(content: str = None):
    """执行一次完整摇卦"""
    try:
        from yijing import YijingDivination
        result = YijingDivination.divinate()
        data = result.to_dict()
        if content:
            data['content'] = content
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Yijing divination error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/yijing/hexagrams")
async def get_all_hexagrams():
    """获取所有六十四卦数据"""
    from yijing import LIU_SHI_SI_GUA_DETAILS
    return {"status": "success", "hexagrams": LIU_SHI_SI_GUA_DETAILS}

@app.get("/api/yijing/bagua")
async def get_bagua():
    """获取八卦信息"""
    from yijing import BA_GUA
    return {"status": "success", "bagua": BA_GUA}

@app.get("/api/yijing/hexagram/{name}")
async def get_hexagram_by_name(name: str):
    """根据卦名获取详细信息"""
    from yijing import LIU_SHI_SI_GUA_DETAILS, YAO_TEXTS
    if name in LIU_SHI_SI_GUA_DETAILS:
        hexagram = LIU_SHI_SI_GUA_DETAILS[name]
        yao_texts = YAO_TEXTS.get(name, {})
        return {
            "status": "success",
            "hexagram": hexagram,
            "yao_texts": {k: v for k, v in yao_texts.items() if isinstance(k, int)}
        }
    return {"status": "error", "message": "卦象不存在"}

async def _generate_yijing_explain(content: str, original: dict, changed: dict, yao_results: list, change_count: int, change_yao_positions: list):
    """生成AI解卦内容（公共逻辑）"""
    from fastapi.responses import StreamingResponse
    import asyncio
    import json
    
    async def generate():
        try:
            configured_models = [m for m in model_manager.get_all() if m.api_key and m.enabled]
            if not configured_models:
                yield f"data: {{\"status\": \"error\", \"message\": \"请先配置至少一个模型的API密钥\"}}\n\n"
                return
            
            import random
            model = random.choice(configured_models)
            adapter = create_llm_adapter(model)
            if not adapter:
                yield f"data: {{\"status\": \"error\", \"message\": \"无法创建模型适配器\"}}\n\n"
                return
            
            yao_desc = "\n".join([
                f"  第{y['position']}爻（{y['name']}）：{y['type']}({y['value']}) - {'阳爻' if y['is_yang'] else '阴爻'}{' - 变爻' if y['is_change'] else ''}"
                for y in yao_results
            ])
            
            prompt = f"""你是一位精通周易的国学大师，请根据以下卦象信息为求测者解卦。

【求测内容】
{content if content else '（未填写）'}

【本卦】
卦名：{original.get('full_name', '')}
卦序：第{original.get('number', '')}卦
卦辞：{original.get('description', '')}

【之卦】{changed.get('full_name', '（无变卦）')}
{changed.get('description', '') if changed else ''}

【六爻详情】（从下往上：初爻→上爻）
{yao_desc}

变爻数：{change_count}
变爻位置：{', '.join([f'第{p}爻' for p in change_yao_positions]) if change_yao_positions else '无'}

请按照以下格式进行解卦：

一、卦象总览
（简要介绍本卦和之卦的基本含义）

二、变爻分析
（分析变爻的具体含义和影响）

三、运势解读
（从事业、财运、感情、健康等方面进行解读）

四、建议与启示
（给求测者的具体建议）

请用通俗易懂的语言，结合卦辞和爻辞进行深入解读，字数不少于500字。"""
            
            messages = [{"role": "user", "content": prompt}]
            
            yield f"data: {{\"status\": \"started\", \"model\": \"{model.name}\", \"prompt\": {json.dumps(prompt, ensure_ascii=False)}}}\n\n"
            
            for chunk in adapter.chat_stream(messages):
                yield f"data: {{\"status\": \"stream\", \"chunk\": {json.dumps(chunk, ensure_ascii=False)}}}\n\n"
                await asyncio.sleep(0.01)
            
            yield f"data: {{\"status\": \"completed\", \"model\": \"{model.name}\", \"prompt\": {json.dumps(prompt, ensure_ascii=False)}}}\n\n"
            
        except Exception as e:
            logger.error(f"Yijing AI explain error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {{\"status\": \"error\", \"message\": \"{str(e)}\"}}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/yijing/ai-explain")
async def yijing_ai_explain(request: Request):
    """AI解卦 - 流式返回（POST方式）"""
    import json
    
    try:
        request_data = await request.json()
    except Exception:
        from fastapi.responses import StreamingResponse
        async def error_gen():
            yield f"data: {{\"status\": \"error\", \"message\": \"请求体解析失败\"}}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")
    
    return await _generate_yijing_explain(
        content=request_data.get("content", "") or "",
        original=request_data.get("original") or {},
        changed=request_data.get("changed") or {},
        yao_results=request_data.get("yao_results") or [],
        change_count=request_data.get("change_count") or 0,
        change_yao_positions=request_data.get("change_yao_positions") or []
    )

@app.get("/api/yijing/ai-explain-stream")
async def yijing_ai_explain_stream(data: str):
    """AI解卦 - SSE流式返回（GET方式，供EventSource使用）"""
    import json
    try:
        request_data = json.loads(data)
    except Exception as e:
        from fastapi.responses import StreamingResponse
        async def error_gen():
            yield f"data: {{\"status\": \"error\", \"message\": \"参数解析失败\"}}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")
    
    return await _generate_yijing_explain(
        content=request_data.get("content", ""),
        original=request_data.get("original", {}),
        changed=request_data.get("changed", {}),
        yao_results=request_data.get("yao_results", []),
        change_count=request_data.get("change_count", 0),
        change_yao_positions=request_data.get("change_yao_positions", [])
    )

# ============ AI聊天 API ============
@app.get("/api/ai-chat/agents")
async def ai_chat_get_agents(refresh: bool = False):
    """获取可用的agent列表"""
    try:
        from ai_chat_manager import ai_chat_manager
        if refresh:
            ai_chat_manager.refresh_agents()
        agents = ai_chat_manager.get_available_agents()
        return {"status": "success", "data": agents}
    except Exception as e:
        logger.error(f"AI chat get agents error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ai-chat/models")
async def ai_chat_get_models():
    """获取可用的模型列表"""
    try:
        from ai_chat_manager import ai_chat_manager
        models = ai_chat_manager.get_available_models()
        return {"status": "success", "data": models}
    except Exception as e:
        logger.error(f"AI chat get models error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/ai-chat/add-role")
async def ai_chat_add_role(request: Request):
    """添加角色到聊天列表"""
    try:
        request_data = await request.json()
        agent_id = request_data.get("agent_id")
        from ai_chat_manager import ai_chat_manager
        role = ai_chat_manager.add_role(agent_id)
        if role:
            return {"status": "success", "data": role.to_dict()}
        else:
            return {"status": "error", "message": "添加角色失败"}
    except Exception as e:
        logger.error(f"AI chat add role error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/ai-chat/remove-role")
async def ai_chat_remove_role(request: Request):
    """从聊天列表移除角色"""
    try:
        request_data = await request.json()
        agent_id = request_data.get("agent_id")
        from ai_chat_manager import ai_chat_manager
        success = ai_chat_manager.remove_role(agent_id)
        return {"status": "success" if success else "error", "data": {"agent_id": agent_id}}
    except Exception as e:
        logger.error(f"AI chat remove role error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ai-chat/roles")
async def ai_chat_get_roles():
    """获取当前角色列表"""
    try:
        from ai_chat_manager import ai_chat_manager
        roles = ai_chat_manager.get_roles()
        return {"status": "success", "data": roles}
    except Exception as e:
        logger.error(f"AI chat get roles error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ai-chat/messages")
async def ai_chat_get_messages():
    """获取聊天消息"""
    try:
        from ai_chat_manager import ai_chat_manager
        messages = ai_chat_manager.get_messages()
        return {"status": "success", "data": messages}
    except Exception as e:
        logger.error(f"AI chat get messages error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/ai-chat/start")
async def ai_chat_start(request: Request):
    """启动聊天"""
    try:
        request_data = await request.json()
        theme = request_data.get("theme", "")
        from ai_chat_manager import ai_chat_manager
        success = await ai_chat_manager.start_chat(theme)
        if success:
            return {"status": "success", "data": {"theme": ai_chat_manager.current_theme}}
        else:
            return {"status": "error", "message": "启动聊天失败，请确保至少添加2个角色"}
    except Exception as e:
        logger.error(f"AI chat start error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/ai-chat/stop")
async def ai_chat_stop():
    """停止聊天"""
    try:
        from ai_chat_manager import ai_chat_manager
        await ai_chat_manager.stop_chat()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"AI chat stop error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ai-chat/status")
async def ai_chat_status():
    """获取聊天状态"""
    try:
        from ai_chat_manager import ai_chat_manager
        status = ai_chat_manager.get_status()
        return {"status": "success", "data": status}
    except Exception as e:
        logger.error(f"AI chat status error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ai-chat/generate-theme")
async def ai_chat_generate_theme():
    """生成随机聊天主题"""
    try:
        from ai_chat_manager import ai_chat_manager
        theme = await ai_chat_manager.generate_theme()
        return {"status": "success", "data": {"theme": theme}}
    except Exception as e:
        logger.error(f"AI chat generate theme error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ai-chat/events")
async def ai_chat_events(request: Request):
    """SSE事件流，实时推送聊天消息"""
    import asyncio as sse_asyncio
    from fastapi.responses import StreamingResponse
    from ai_chat_manager import ai_chat_manager
    
    event_queue = sse_asyncio.Queue()
    
    async def callback(event_type, data):
        await event_queue.put({"event": event_type, "data": data})
    
    ai_chat_manager.add_callback(callback)
    
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                
                try:
                    event_data = await sse_asyncio.wait_for(event_queue.get(), timeout=0.5)
                    message = f"data: {json.dumps(event_data)}\n\n"
                    yield message
                except sse_asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            ai_chat_manager.remove_callback(callback)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ============ AI聊天历史记录 API ============

@app.get("/api/ai-chat/history")
async def ai_chat_get_history(limit: int = 50):
    """获取聊天记录列表"""
    try:
        from ai_chat_manager import ai_chat_manager
        history = ai_chat_manager.get_history_list(limit)
        return {"status": "success", "data": history}
    except Exception as e:
        logger.error(f"AI chat get history error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ai-chat/history/{session_id}")
async def ai_chat_get_history_detail(session_id: str):
    """获取单条聊天记录的详细信息"""
    try:
        from ai_chat_manager import ai_chat_manager
        detail = ai_chat_manager.get_history_detail(session_id)
        if detail:
            return {"status": "success", "data": detail}
        else:
            return {"status": "error", "message": "聊天记录不存在"}
    except Exception as e:
        logger.error(f"AI chat get history detail error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/ai-chat/history/delete")
async def ai_chat_delete_history(request: Request):
    """删除某条聊天记录"""
    try:
        request_data = await request.json()
        session_id = request_data.get("session_id")
        if not session_id:
            return {"status": "error", "message": "缺少session_id"}
        
        from ai_chat_manager import ai_chat_manager
        if ai_chat_manager.delete_history(session_id):
            return {"status": "success", "message": "删除成功"}
        else:
            return {"status": "error", "message": "删除失败"}
    except Exception as e:
        logger.error(f"AI chat delete history error: {e}")
        return {"status": "error", "message": str(e)}


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