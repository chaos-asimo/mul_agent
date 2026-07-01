"""Model manager for CRUD operations"""
import json
import os
from typing import List, Optional, Dict
from .model_config import ModelConfig


class ModelManager:
    """Manages LLM model configurations"""

    DEFAULT_MODELS = [
        ModelConfig(
            id="default_openai",
            name="OpenAI GPT-4",
            api_type="openai",
            model_type="text",
            api_url="https://api.openai.com/v1",
            api_key="",
            model_name="gpt-4"
        ),
        ModelConfig(
            id="default_claude",
            name="Claude 3",
            api_type="anthropic",
            model_type="text",
            api_url="https://api.anthropic.com/v1",
            api_key="",
            model_name="claude-3-opus-20240229"
        ),
        ModelConfig(
            id="default_deepseek",
            name="DeepSeek Chat",
            api_type="deepseek",
            model_type="text",
            api_url="https://api.deepseek.com/v1",
            api_key="",
            model_name="deepseek-chat"
        ),
        ModelConfig(
            id="default_dalle",
            name="DALL-E 3",
            api_type="dall-e",
            model_type="image",
            api_url="https://api.openai.com/v1",
            api_key="",
            model_name="dall-e-3"
        ),
        ModelConfig(
            id="default_sd",
            name="Stable Diffusion",
            api_type="stable-diffusion",
            model_type="image",
            api_url="https://api.stability.ai/v2beta",
            api_key="",
            model_name="sd3-medium"
        ),
    ]

    def __init__(self, config_path: str = "models.json"):
        self.config_path = config_path
        self.models: List[ModelConfig] = []
        self.load()

    def load(self):
        """Load models from file or create defaults"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.models = [ModelConfig.from_dict(m) for m in data]
                return
            except (json.JSONDecodeError, KeyError):
                pass
        self.models = self.DEFAULT_MODELS.copy()
        self.save()

    def save(self):
        """Save models to file"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump([m.to_dict() for m in self.models], f, ensure_ascii=False, indent=2)

    def add(self, model: ModelConfig) -> bool:
        """Add a new model"""
        if any(m.id == model.id for m in self.models):
            return False
        self.models.append(model)
        self.save()
        return True

    def update(self, model: ModelConfig) -> bool:
        """Update an existing model"""
        for i, m in enumerate(self.models):
            if m.id == model.id:
                self.models[i] = model
                self.save()
                return True
        return False

    def delete(self, model_id: str) -> bool:
        """Delete a model"""
        for i, m in enumerate(self.models):
            if m.id == model_id:
                del self.models[i]
                self.save()
                return True
        return False

    def get(self, model_id: str) -> Optional[ModelConfig]:
        """Get a model by ID"""
        for m in self.models:
            if m.id == model_id:
                return m
        return None

    def get_all(self) -> List[ModelConfig]:
        """Get all models"""
        return self.models.copy()

    def get_by_type(self, api_type: str) -> List[ModelConfig]:
        """Get models by API type"""
        return [m for m in self.models if m.api_type == api_type]

    def to_dict_list(self) -> List[Dict]:
        """Convert all models to dict list for UI"""
        return [m.to_dict() for m in self.models]
