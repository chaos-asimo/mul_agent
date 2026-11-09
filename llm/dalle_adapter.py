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
        start_time = time.time()
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

                self._log(prompt, f"[image] {local_image_url or image_url}", time.time() - start_time)
                return ImageResponse(
                    success=True,
                    image_url=local_image_url
                )

            self._log(prompt, "", time.time() - start_time, error="No image data returned")
            return ImageResponse(success=False, error="No image data returned")

        except Exception as e:
            self._log(prompt, "", time.time() - start_time, error=str(e))
            return ImageResponse(success=False, error=str(e))

    def _log(self, prompt: str, response_text: str, duration: float, error: str = None):
        """图像生成调用计入模型调用日志（无 token 用量，记录耗时与结果）。"""
        try:
            from .model_call_logger import model_call_logger
            model_call_logger.log_call(
                model_name=self.model_name,
                messages=[{"role": "user", "content": f"[image_generation] {prompt}"}],
                response=response_text,
                total_tokens=0, prompt_tokens=0, completion_tokens=0,
                duration=duration, error=error,
            )
        except Exception:
            pass
    
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
