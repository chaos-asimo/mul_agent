"""Image generation adapter base class"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict


@dataclass
class ImageResponse:
    """Response from image generation"""
    success: bool
    image_url: str = ""
    image_data: bytes = b""
    error: str = ""
    
    def to_dict(self):
        return asdict(self)


class ImageAdapter(ABC):
    """Base adapter for image generation models"""
    
    def __init__(self, api_key: str, api_url: str, model_name: str):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> ImageResponse:
        """Generate an image from text prompt"""
        pass
