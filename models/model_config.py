"""Model configuration data class"""
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class ModelConfig:
    """LLM Model configuration"""
    id: str = ""
    name: str = ""
    api_type: str = "openai"  # openai, claude, deepseek, dall-e, sd, custom
    model_type: str = "text"  # text, image, video
    api_url: str = ""
    api_key: str = ""
    model_name: str = ""
    max_tokens: int = 4000
    context_window: int = 4000
    enabled: bool = True

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ModelConfig":
        return cls(**data)

    def save_to_file(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> Optional["ModelConfig"]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except FileNotFoundError:
            return None
