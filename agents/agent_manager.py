"""Agent manager for CRUD operations"""
import json
import os
from typing import List, Optional, Dict
from .agent_config import AgentConfig
from prompts import (
    AGENT_ROLE_EDITOR,
    AGENT_ROLE_EXPANDER,
    AGENT_ROLE_POLISHER,
    AGENT_ROLE_REVIEWER,
)


class AgentManager:
    """Manages Agent configurations"""

    DEFAULT_AGENTS = [
        AgentConfig(
            id="editor",
            name="编辑",
            role_description=AGENT_ROLE_EDITOR,
            model_id="default_openai",
            enabled=True,
            order=0
        ),
        AgentConfig(
            id="reviewer",
            name="审核",
            role_description=AGENT_ROLE_REVIEWER,
            model_id="default_openai",
            enabled=True,
            order=1
        ),
        AgentConfig(
            id="expander",
            name="扩展",
            role_description=AGENT_ROLE_EXPANDER,
            model_id="default_openai",
            enabled=True,
            order=2
        ),
        AgentConfig(
            id="polisher",
            name="润色",
            role_description=AGENT_ROLE_POLISHER,
            model_id="default_openai",
            enabled=True,
            order=3
        ),
    ]

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "..", "agents.json")
        self.config_path = os.path.abspath(config_path)
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
