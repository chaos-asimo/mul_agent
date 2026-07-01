"""Stable Diffusion image generation adapter"""
import requests
from .image_adapter import ImageAdapter, ImageResponse


class StableDiffusionAdapter(ImageAdapter):
    """Adapter for Stability AI Stable Diffusion"""
    
    def generate(self, prompt: str, **kwargs) -> ImageResponse:
        """Generate image using Stable Diffusion"""
        try:
            url = f"{self.api_url}/image/generate/sd3"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "prompt": prompt,
                "model": self.model_name,
                "output_format": kwargs.get("output_format", "png"),
                "aspect_ratio": kwargs.get("aspect_ratio", "1:1"),
                "seed": kwargs.get("seed", 0),
                "negative_prompt": kwargs.get("negative_prompt", "")
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("image"):
                return ImageResponse(
                    success=True,
                    image_data=result["image"]
                )
            
            return ImageResponse(success=False, error="No image data returned")
            
        except Exception as e:
            return ImageResponse(success=False, error=str(e))
