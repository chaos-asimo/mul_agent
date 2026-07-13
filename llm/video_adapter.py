"""Video generation adapter - Agnes Video API compatible"""
import os
import time
import logging
import requests

logger = logging.getLogger(__name__)


class VideoResponse:
    """Response from video generation"""
    def __init__(self, success: bool = False, video_url: str = "", video_data: bytes = None, 
                 error: str = "", video_id: str = "", task_id: str = "", 
                 status: str = "", progress: int = 0):
        self.success = success
        self.video_url = video_url
        self.video_data = video_data
        self.error = error
        self.video_id = video_id
        self.task_id = task_id
        self.status = status
        self.progress = progress


class VideoAdapter:
    """Base class for video generation adapters"""
    
    def __init__(self, api_key: str, api_url: str, model_name: str):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "videos")
        os.makedirs(self.upload_dir, exist_ok=True)
    
    def generate(self, prompt: str, **kwargs) -> VideoResponse:
        """Create video generation task"""
        raise NotImplementedError
    
    def get_status(self, video_id: str) -> dict:
        """Get video generation status"""
        raise NotImplementedError
    
    def _save_video_locally(self, video_url: str, filename: str = None) -> str:
        """Download video from URL and save to local server"""
        try:
            if not video_url:
                return ""
            
            # If already a local path, return as-is
            if video_url.startswith("/uploads/"):
                return video_url
            
            # Download the video
            video_response = requests.get(video_url, timeout=300, stream=True)
            video_response.raise_for_status()
            
            # Use provided filename or generate one
            if not filename:
                timestamp = int(time.time())
                ext = ".mp4"
                for content_type in video_response.headers.get("Content-Type", "").split(";"):
                    if "video" in content_type:
                        if "mp4" in content_type:
                            ext = ".mp4"
                        elif "webm" in content_type:
                            ext = ".webm"
                        elif "mov" in content_type:
                            ext = ".mov"
                        break
                filename = f"vid_{timestamp}_{os.urandom(4).hex()}{ext}"
            
            filepath = os.path.join(self.upload_dir, filename)
            
            # Save to local
            with open(filepath, "wb") as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Return relative URL
            return f"/uploads/videos/{filename}"
        except Exception as e:
            # If saving fails, return original URL
            return video_url


class AgnesVideoAdapter(VideoAdapter):
    """Adapter for Agnes Video API"""
    
    def __init__(self, api_key: str, api_url: str = None, model_name: str = "agnes-video-v2.0"):
        super().__init__(api_key, api_url or "https://apihub.agnes-ai.com", model_name)
    
    def generate(self, prompt: str, **kwargs) -> VideoResponse:
        """Create video generation task using Agnes Video API"""
        try:
            base_url = self.api_url.rstrip("/")
            if base_url.endswith("/v1/videos"):
                base_url = base_url.rsplit("/v1/videos", 1)[0]
            elif base_url.endswith("/v1"):
                base_url = base_url.rsplit("/v1", 1)[0]
            url = f"{base_url}/v1/videos"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model_name,
                "prompt": prompt,
                "width": kwargs.get("width", 1152),
                "height": kwargs.get("height", 768),
                "num_frames": kwargs.get("num_frames", 121),
                "frame_rate": kwargs.get("frame_rate", 24)
            }
            
            # Add optional parameters
            if kwargs.get("image"):
                data["image"] = kwargs["image"]
            elif kwargs.get("image_url"):
                data["image"] = kwargs["image_url"]
            
            if kwargs.get("negative_prompt"):
                data["negative_prompt"] = kwargs["negative_prompt"]
            
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            
            video_id = result.get("video_id", "")
            task_id = result.get("task_id", result.get("id", ""))
            
            if video_id or task_id:
                return VideoResponse(
                    success=True,
                    video_id=video_id,
                    task_id=task_id,
                    status=result.get("status", "queued"),
                    progress=result.get("progress", 0)
                )
            
            return VideoResponse(success=False, error="No video_id or task_id returned")
            
        except Exception as e:
            return VideoResponse(success=False, error=str(e))
    
    def get_status(self, video_id: str) -> dict:
        """Get video generation status using Agnes Video API"""
        try:
            # 使用推荐的查询方式：只需要 video_id
            # self.api_url 可能是 https://apihub.agnes-ai.com 或 https://apihub.agnes-ai.com/v1/videos
            base_url = self.api_url.rstrip("/")
            if base_url.endswith("/v1/videos"):
                base_url = base_url.rsplit("/v1/videos", 1)[0]
            url = f"{base_url}/agnesapi"
            params = {"video_id": video_id}
            
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            logger.info(f"查询视频状态: video_id={video_id}, url={url}, params={params}")
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            logger.info(f"API响应状态码: {response.status_code}")
            
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"API返回数据: {result}")
            
            status = result.get("status", "unknown")
            progress = result.get("progress", 0)
            # 优先使用 'url' 字段，其次 'remixed_from_video_id'
            remote_video_url = result.get("url") or result.get("remixed_from_video_id", "")
            
            # 如果视频生成完成且有URL，下载到本地（只在第一次下载）
            local_video_url = ""
            if status == "completed" and remote_video_url:
                # 使用远程URL的原始文件名，确保多次查询时文件名一致
                video_filename = remote_video_url.split('/')[-1]
                # 移除可能的查询参数
                if '?' in video_filename:
                    video_filename = video_filename.split('?')[0]
                # 确保有扩展名
                if not any(video_filename.endswith(ext) for ext in ['.mp4', '.webm', '.mov']):
                    video_filename += '.mp4'
                
                local_path = os.path.join(self.upload_dir, video_filename)
                if os.path.exists(local_path):
                    # 文件已存在，直接使用本地路径
                    local_video_url = f"/uploads/videos/{video_filename}"
                    logger.info(f"视频已存在，直接使用: {local_video_url}")
                else:
                    logger.info(f"视频已完成，开始下载: {remote_video_url}")
                    local_video_url = self._save_video_locally(remote_video_url, video_filename)
                    logger.info(f"本地保存路径: {local_video_url}")
            
            return {
                "video_id": video_id,
                "status": status,
                "progress": progress,
                "video_url": local_video_url or remote_video_url,
                "error": result.get("error"),
                "seconds": result.get("seconds"),
                "size": result.get("size")
            }
            
        except Exception as e:
            logger.error(f"查询视频状态失败: {e}")
            return {
                "video_id": video_id,
                "status": "error",
                "progress": 0,
                "error": str(e)
            }


class OpenAIVideoAdapter(VideoAdapter):
    """Adapter for OpenAI-compatible video generation APIs"""
    
    def generate(self, prompt: str, **kwargs) -> VideoResponse:
        """Generate video using OpenAI-compatible API"""
        try:
            base_url = self.api_url.rstrip("/")
            url = f"{base_url}/videos/generate"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model_name,
                "prompt": prompt,
                "duration": kwargs.get("duration", 5),
                "resolution": kwargs.get("resolution", "720p")
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            
            video_url = result.get("video_url", result.get("url", ""))
            if video_url:
                local_url = self._save_video_locally(video_url)
                return VideoResponse(success=True, video_url=local_url)
            
            return VideoResponse(success=False, error="No video URL returned")
            
        except Exception as e:
            return VideoResponse(success=False, error=str(e))
    
    def get_status(self, video_id: str) -> dict:
        """Get video generation status using OpenAI-compatible API"""
        try:
            base_url = self.api_url.rstrip("/")
            url = f"{base_url}/videos/status/{video_id}"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            return {
                "video_id": video_id,
                "status": result.get("status", "unknown"),
                "progress": result.get("progress", 0),
                "video_url": result.get("video_url", result.get("url", "")),
                "error": result.get("error")
            }
            
        except Exception as e:
            logger.error(f"查询视频状态失败: {e}")
            return {
                "video_id": video_id,
                "status": "error",
                "progress": 0,
                "error": str(e)
            }
