"""Agent manager for CRUD operations"""
import json
import os
from typing import List, Optional, Dict
from .agent_config import AgentConfig


class AgentManager:
    """Manages Agent configurations"""

    DEFAULT_AGENTS = [
        AgentConfig(
            id="editor",
            name="编辑",
            role_description="""你是一位专业的文档编辑。你的任务是：
1. 检查并修正文本中的语法错误
2. 改善句子结构和表达清晰度
3. 保持原文的风格和意图
4. 使文章更加流畅易读

请直接输出修改后的内容，不要添加额外说明。""",
            model_id="default_openai",
            enabled=True,
            order=0
        ),
        AgentConfig(
            id="reviewer",
            name="审核",
            role_description="""你是一位资深的内容审核专家。你的任务是：
1. 检查文档的逻辑连贯性
2. 指出潜在的错误或不一致
3. 提供改进建议
4. 确保内容的准确性和专业性

请直接输出审核意见和改进后的内容，不要添加额外说明。""",
            model_id="default_openai",
            enabled=True,
            order=1
        ),
        AgentConfig(
            id="expander",
            name="扩展",
            role_description="""你是一位创意写作专家。你的任务是：
1. 在保持核心信息的同时适度扩展内容
2. 添加相关但未提及的要点
3. 提供更多细节和例子
4. 丰富文档的深度和广度

请直接输出扩展后的内容，不要添加额外说明。""",
            model_id="default_openai",
            enabled=True,
            order=2
        ),
        AgentConfig(
            id="polisher",
            name="润色",
            role_description="""你是一位文字润色专家。你的任务是：
1. 优化用词选择
2. 提升文字的艺术感和表现力
3. 平衡语气和风格
4. 使文档更加专业和有吸引力

请直接输出润色后的内容，不要添加额外说明。""",
            model_id="default_openai",
            enabled=True,
            order=3
        ),
    ]

    def __init__(self, config_path: str = "agents.json"):
        self.config_path = config_path
        self.agents: List[AgentConfig] = []
        self.load()

    def load(self):
        """Load agents from file or create defaults"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.agents = [AgentConfig.from_dict(a) for a in data]
                return
            except (json.JSONDecodeError, KeyError):
                pass
        self.agents = self.DEFAULT_AGENTS.copy()
        self.save()

    def save(self):
        """Save agents to file"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump([a.to_dict() for a in self.agents], f, ensure_ascii=False, indent=2)

    def add(self, agent: AgentConfig) -> bool:
        """Add a new agent"""
        if any(a.id == agent.id for a in self.agents):
            return False
        self.agents.append(agent)
        self.save()
        return True

    def update(self, agent: AgentConfig) -> bool:
        """Update an existing agent"""
        for i, a in enumerate(self.agents):
            if a.id == agent.id:
                self.agents[i] = agent
                self.save()
                return True
        return False

    def delete(self, agent_id: str) -> bool:
        """Delete an agent"""
        for i, a in enumerate(self.agents):
            if a.id == agent_id:
                del self.agents[i]
                self.save()
                return True
        return False

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """Get an agent by ID"""
        for a in self.agents:
            if a.id == agent_id:
                return a
        return None

    def get_all(self) -> List[AgentConfig]:
        """Get all agents"""
        return self.agents.copy()

    def get_enabled(self) -> List[AgentConfig]:
        """Get enabled agents sorted by order"""
        return sorted([a for a in self.agents if a.enabled], key=lambda x: x.order)

    def to_dict_list(self) -> List[Dict]:
        """Convert all agents to dict list for UI"""
        return [a.to_dict() for a in self.agents]
