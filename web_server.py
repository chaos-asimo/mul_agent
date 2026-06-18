"""Multi-Agent Document Enhancer Web Server"""
import os
import asyncio
import sys
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, File, UploadFile, Form
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
settings = {
    "iterations": 1,
    "enable_search": True,
    "max_search_per_iter": 3,

}

# 版本号（直接定义在代码中，更新时修改此值）
app_version = "v1.20260617.154530"
logger.info(f"App version: {app_version}")

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

class SettingsUpdate(BaseModel):
    iterations: int
    enable_search: bool
    max_search_per_iter: int
    default_log_level: str

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页面"""
    models = [m.to_dict() for m in model_manager.get_all()]
    agents = [a.to_dict() for a in agent_manager.get_all()]
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
        enabled=config.enabled
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
        enabled=config.enabled
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
    total_agents = len(enabled_agents)
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
            "total_tokens": controller.state.total_tokens,
            "search_count": controller.state.search_count,
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
    
    # 重置控制器状态
    if controller:
        controller.state.is_running = False
        controller.state.current_iteration = 0
        controller.state.current_agent_index = 0
        controller.state.current_agent_name = ""
        controller.state.current_model_name = ""
        controller.state.total_tokens = 0
        controller.state.search_count = 0
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