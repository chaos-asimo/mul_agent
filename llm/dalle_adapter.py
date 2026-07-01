"""DALL-E image generation adapter"""
import os
import time
import requests
from .image_adapter import ImageAdapter, ImageResponse


class DALLEAdapter(ImageAdapter):
    """Adapter for OpenAI DALL-E image generation"""
    
    def __init__(self, api_key: str, api_url: str, model_name: str):
        super().__init__(api_key, api_url, model_name)
        self.upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "images")
        os.makedirs(self.upload_dir, exist_ok=True)
    
    def generate(self, prompt: str, **kwargs) -> ImageResponse:
        """Generate image using DALL-E"""
        try:
            # Avoid duplicate path suffix: if api_url already ends with /images/generations, use it directly
            base_url = self.api_url.rstrip("/")
            if base_url.endswith("/images/generations"):
                url = base_url
            else:
                url = f"{base_url}/images/generations"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model_name,
                "prompt": prompt,
                "n": kwargs.get("n", 1),
                "size": kwargs.get("size", "1024x1024")
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("data") and len(result["data"]) > 0:
                image_url = result["data"][0].get("url", "")
                
                # Download image and save to local server
                local_image_url = self._save_image_locally(image_url)
                
                return ImageResponse(
                    success=True,
                    image_url=local_image_url
                )
            
            return ImageResponse(success=False, error="No image data returned")
            
        except Exception as e:
            return ImageResponse(success=False, error=str(e))
    
    def _save_image_locally(self, image_url: str) -> str:
        """Download image from URL and save to local server"""
        try:
            if not image_url:
                return ""
            
            # If already a local path, return as-is
            if image_url.startswith("/uploads/"):
                return image_url
            
            # Download the image
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            
            # Generate filename
            timestamp = int(time.time())
            filename = f"img_{timestamp}_{os.urandom(4).hex()}.png"
            filepath = os.path.join(self.upload_dir, filename)
            
            # Save to local
            with open(filepath, "wb") as f:
                f.write(img_response.content)
            
            # Return relative URL
            return f"/uploads/images/{filename}"
        except Exception as e:
            # If saving fails, return original URL
            return image_url
