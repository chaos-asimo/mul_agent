"""Skill配置模块"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import json
import uuid


class SkillType(Enum):
    """Skill类型"""
    SEARCH = "search"           # 搜索类
    ANALYSIS = "analysis"       # 分析类
    GENERATION = "generation"   # 生成类
    TRANSFORMATION = "transform" # 转换类
    VALIDATION = "validation"   # 验证类
    CUSTOM = "custom"           # 自定义类


class SkillTrigger(Enum):
    """Skill触发方式"""
    MANUAL = "manual"           # 手动触发
    AUTO = "auto"               # 自动触发
    CONDITIONAL = "conditional" # 条件触发
    SCHEDULED = "scheduled"     # 定时触发


@dataclass
class SkillParameter:
    """Skill参数定义"""
    name: str
    type: str = "string"        # string, number, boolean, list, object
    required: bool = False
    default: Any = None
    description: str = ""
    options: List[str] = field(default_factory=list)  # 可选值列表


@dataclass
class SkillConfig:
    """Skill配置"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    skill_type: SkillType = SkillType.CUSTOM
    trigger: SkillTrigger = SkillTrigger.MANUAL
    enabled: bool = True
    
    # 执行相关
    executor: str = ""          # 执行器类型: python, llm, search, api
    script: str = ""            # Python脚本路径或代码
    prompt_template: str = ""   # LLM提示模板
    api_endpoint: str = ""      # API端点
    
    # 参数定义
    parameters: List[SkillParameter] = field(default_factory=list)
    
    # 输入输出
    input_type: str = "text"    # text, json, file
    output_type: str = "text"   # text, json, file
    
    # 依赖关系
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他skill id
    pre_conditions: List[str] = field(default_factory=list) # 前置条件
    
    # 元数据
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    icon: str = "fas fa-cog"    # FontAwesome图标
    
    # 执行配置
    timeout: int = 60           # 超时时间(秒)
    retry_count: int = 3        # 重试次数
    priority: int = 0           # 优先级
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skill_type": self.skill_type.value,
            "trigger": self.trigger.value,
            "enabled": self.enabled,
            "executor": self.executor,
            "script": self.script,
            "prompt_template": self.prompt_template,
            "api_endpoint": self.api_endpoint,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                    "options": p.options
                }
                for p in self.parameters
            ],
            "input_type": self.input_type,
            "output_type": self.output_type,
            "dependencies": self.dependencies,
            "pre_conditions": self.pre_conditions,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "icon": self.icon,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "priority": self.priority
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillConfig:
        """从字典创建"""
        parameters = [
            SkillParameter(
                name=p.get("name", ""),
                type=p.get("type", "string"),
                required=p.get("required", False),
                default=p.get("default"),
                description=p.get("description", ""),
                options=p.get("options", [])
            )
            for p in data.get("parameters", [])
        ]
        
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            skill_type=SkillType(data.get("skill_type", "custom")),
            trigger=SkillTrigger(data.get("trigger", "manual")),
            enabled=data.get("enabled", True),
            executor=data.get("executor", ""),
            script=data.get("script", ""),
            prompt_template=data.get("prompt_template", ""),
            api_endpoint=data.get("api_endpoint", ""),
            parameters=parameters,
            input_type=data.get("input_type", "text"),
            output_type=data.get("output_type", "text"),
            dependencies=data.get("dependencies", []),
            pre_conditions=data.get("pre_conditions", []),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            icon=data.get("icon", "fas fa-cog"),
            timeout=data.get("timeout", 60),
            retry_count=data.get("retry_count", 3),
            priority=data.get("priority", 0)
        )


# 预定义的Skills
DEFAULT_SKILLS = [
    SkillConfig(
        name="联网搜索",
        description="使用Tavily搜索引擎进行联网搜索，获取最新信息",
        skill_type=SkillType.SEARCH,
        trigger=SkillTrigger.MANUAL,
        executor="search",
        icon="fas fa-search",
        parameters=[
            SkillParameter(name="query", type="string", required=True, description="搜索关键词"),
            SkillParameter(name="num_results", type="number", default=5, description="返回结果数量")
        ],
        tags=["搜索", "联网", "信息获取"]
    ),
    SkillConfig(
        name="内容分析",
        description="使用AI模型分析文本内容，提取关键信息",
        skill_type=SkillType.ANALYSIS,
        trigger=SkillTrigger.MANUAL,
        executor="llm",
        icon="fas fa-brain",
        prompt_template="请分析以下内容，提取关键要点：\n{content}",
        parameters=[
            SkillParameter(name="content", type="string", required=True, description="待分析内容"),
            SkillParameter(name="analysis_type", type="string", default="summary", 
                          options=["summary", "keywords", "sentiment", "structure"],
                          description="分析类型")
        ],
        tags=["分析", "AI", "内容处理"]
    ),
    SkillConfig(
        name="文本生成",
        description="使用AI模型根据模板生成文本内容",
        skill_type=SkillType.GENERATION,
        trigger=SkillTrigger.MANUAL,
        executor="llm",
        icon="fas fa-pen-fancy",
        prompt_template="请根据以下要求生成内容：\n{requirements}\n\n参考信息：\n{context}",
        parameters=[
            SkillParameter(name="requirements", type="string", required=True, description="生成要求"),
            SkillParameter(name="context", type="string", description="参考上下文"),
            SkillParameter(name="style", type="string", default="professional",
                          options=["professional", "casual", "academic", "creative"],
                          description="写作风格")
        ],
        tags=["生成", "AI", "写作"]
    ),
    SkillConfig(
        name="格式转换",
        description="将文本转换为指定格式（Markdown、HTML、JSON等）",
        skill_type=SkillType.TRANSFORMATION,
        trigger=SkillTrigger.MANUAL,
        executor="llm",
        icon="fas fa-exchange-alt",
        prompt_template="请将以下内容转换为{format}格式：\n{content}",
        parameters=[
            SkillParameter(name="content", type="string", required=True, description="待转换内容"),
            SkillParameter(name="format", type="string", default="markdown",
                          options=["markdown", "html", "json", "plain"],
                          description="目标格式")
        ],
        tags=["转换", "格式", "处理"]
    ),
    SkillConfig(
        name="内容验证",
        description="验证内容是否符合指定标准和规范",
        skill_type=SkillType.VALIDATION,
        trigger=SkillTrigger.MANUAL,
        executor="llm",
        icon="fas fa-check-circle",
        prompt_template="请验证以下内容是否符合{standard}标准：\n{content}\n\n列出发现的问题和改进建议。",
        parameters=[
            SkillParameter(name="content", type="string", required=True, description="待验证内容"),
            SkillParameter(name="standard", type="string", default="general",
                          options=["general", "academic", "business", "technical"],
                          description="验证标准")
        ],
        tags=["验证", "检查", "质量"]
    ),
    SkillConfig(
        name="智能问答",
        description="基于上下文的智能问答系统",
        skill_type=SkillType.CUSTOM,
        trigger=SkillTrigger.MANUAL,
        executor="llm",
        icon="fas fa-question-circle",
        prompt_template="基于以下上下文回答问题：\n\n上下文：\n{context}\n\n问题：\n{question}",
        parameters=[
            SkillParameter(name="context", type="string", required=True, description="上下文信息"),
            SkillParameter(name="question", type="string", required=True, description="问题")
        ],
        tags=["问答", "AI", "智能"]
    ),
    SkillConfig(
        name="代码生成",
        description="根据需求生成代码片段",
        skill_type=SkillType.GENERATION,
        trigger=SkillTrigger.MANUAL,
        executor="llm",
        icon="fas fa-code",
        prompt_template="请根据以下需求生成{language}代码：\n{requirements}\n\n要求：\n- 代码清晰易读\n- 包含必要注释\n- 遵循最佳实践",
        parameters=[
            SkillParameter(name="requirements", type="string", required=True, description="代码需求"),
            SkillParameter(name="language", type="string", default="python",
                          options=["python", "javascript", "java", "go", "typescript"],
                          description="编程语言")
        ],
        tags=["代码", "生成", "开发"]
    ),
    SkillConfig(
        name="数据提取",
        description="从文本中提取结构化数据",
        skill_type=SkillType.ANALYSIS,
        trigger=SkillTrigger.MANUAL,
        executor="llm",
        icon="fas fa-filter",
        prompt_template="请从以下文本中提取{data_type}数据，以JSON格式输出：\n{text}",
        parameters=[
            SkillParameter(name="text", type="string", required=True, description="源文本"),
            SkillParameter(name="data_type", type="string", default="general",
                          options=["general", "contacts", "dates", "numbers", "entities"],
                          description="数据类型")
        ],
        tags=["提取", "数据", "结构化"]
    )
]