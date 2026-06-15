"""Search engine configuration data class"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class SearchEngineConfig:
    """Search engine configuration"""
    id: str = ""
    name: str = ""
    adapter_type: str = "bing"  # bing, google, baidu
    api_key: str = ""
    api_url: str = ""
    enabled: bool = True

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchEngineConfig":
        return cls(**data)
