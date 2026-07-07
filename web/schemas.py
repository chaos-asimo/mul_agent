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


class SettingsUpdate(BaseModel):
    iterations: int
    enable_search: bool
    max_search_per_iter: int
    default_log_level: str


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
