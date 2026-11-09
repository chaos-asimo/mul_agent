"""Agent configuration data class"""
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class AgentConfig:
    """Agent configuration"""
    id: str = ""
    name: str = ""
    role_description: str = ""
    model_id: str = ""
    enabled: bool = True
    context_threshold: int = 4000
    order: int = 0

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        return cls(**data)

    def save_to_file(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> Optional["AgentConfig"]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except FileNotFoundError:
            return None
