from pydantic import BaseModel
from typing import List, Optional


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


class ImageGenerateRequest(BaseModel):
    prompt: str
    model_id: Optional[str] = None
    n: int = 1
    size: str = "1024x1024"
    negative_prompt: str = ""


class VideoGenerateRequest(BaseModel):
    prompt: str
    model_id: Optional[str] = None
    width: int = 1152
    height: int = 768
    num_frames: int = 121
    frame_rate: int = 24
    image_url: Optional[str] = None
    negative_prompt: str = ""

    def _validate_num_frames(self) -> int:
        """API 要求 num_frames = 8n + 1（如 9, 17, 25, 33, 41, 49, ...）"""
        if self.num_frames < 1 or (self.num_frames - 1) % 8 != 0:
            n = round((self.num_frames - 1) / 8)
            n = max(0, n)
            self.num_frames = 8 * n + 1
        return self.num_frames
