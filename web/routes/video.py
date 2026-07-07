import os
import time
import random
from fastapi import APIRouter, Request, Depends
from utils.logger import logger
from web.schemas import VideoGenerateRequest
from engine.agent_worker import create_video_adapter, create_llm_adapter

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


video_tasks = {}


@router.post("/video-generate")
async def generate_video(request: VideoGenerateRequest, managers: dict = Depends(get_managers)):
    """文生视频API"""
    model_manager = managers["model_manager"]
    try:
        models = model_manager.get_all()

        if request.model_id:
            model = model_manager.get(request.model_id)
        else:
            video_models = [m for m in models if m.api_key and m.enabled and m.model_type == "video"]
            if not video_models:
                return {"status": "error", "message": "请先配置至少一个文生视频模型"}
            model = video_models[0]

        if model.model_type != "video":
            return {"status": "error", "message": "选择的模型不是文生视频模型"}

        adapter = create_video_adapter(model)
        if not adapter:
            return {"status": "error", "message": "无法创建视频适配器"}

        video_data = {
            "model": model.model_name,
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "num_frames": request.num_frames,
            "frame_rate": request.frame_rate
        }

        if request.image_url:
            video_data["image"] = request.image_url

        if request.negative_prompt:
            video_data["negative_prompt"] = request.negative_prompt

        response = adapter.generate(**video_data)

        if response.success and hasattr(response, 'video_id'):
            video_tasks[response.video_id] = {
                "status": response.status,
                "progress": response.progress,
                "model": model.name,
                "model_id": model.id,
                "created_at": int(time.time())
            }

            return {
                "status": "success",
                "video_id": response.video_id,
                "task_id": response.task_id,
                "message": "视频生成任务已创建，请轮询状态"
            }
        elif response.success and hasattr(response, 'task_id'):
            video_tasks[response.task_id] = {
                "status": response.status,
                "progress": response.progress,
                "model": model.name,
                "model_id": model.id,
                "created_at": int(time.time())
            }

            return {
                "status": "success",
                "video_id": getattr(response, 'video_id', response.task_id),
                "task_id": response.task_id,
                "message": "视频生成任务已创建，请轮询状态"
            }
        else:
            return {"status": "error", "message": f"创建任务失败: {response.error}"}

    except Exception as e:
        logger.error(f"Video generation error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"创建任务失败: {str(e)}"}


@router.get("/video-status/{video_id}")
async def get_video_status(video_id: str, managers: dict = Depends(get_managers)):
    """获取视频生成状态"""
    model_manager = managers["model_manager"]
    try:
        logger.info(f"视频状态查询请求: video_id={video_id}")

        now = int(time.time())

        task = video_tasks.get(video_id)

        if task and task.get("model_id"):
            model_id = task["model_id"]
            models = model_manager.get_all()
            model = next((m for m in models if m.id == model_id), None)
        else:
            models = model_manager.get_all()
            video_models = [m for m in models if m.api_key and m.enabled and m.model_type == "video"]
            if not video_models:
                return {"code": "error", "message": "没有可用的视频模型"}
            model = video_models[0]

        if not model:
            return {"code": "error", "message": f"找不到模型ID: {model_id}"}

        adapter = create_video_adapter(model)
        if not adapter:
            return {"code": "error", "message": "无法创建视频适配器"}

        task_info = adapter.get_status(video_id)
        logger.info(f"适配器返回的任务信息: {task_info}")

        if task_info:
            if video_id in video_tasks:
                video_tasks[video_id].update({
                    "status": task_info.get("status", "unknown"),
                    "progress": task_info.get("progress", 0),
                    "video_url": task_info.get("video_url", ""),
                    "error": task_info.get("error"),
                    "seconds": task_info.get("seconds"),
                    "size": task_info.get("size")
                })
            else:
                video_tasks[video_id] = {
                    "status": task_info.get("status", "unknown"),
                    "progress": task_info.get("progress", 0),
                    "video_url": task_info.get("video_url", ""),
                    "error": task_info.get("error"),
                    "seconds": task_info.get("seconds"),
                    "size": task_info.get("size")
                }

            result = {
                "code": "success",
                "video_id": video_id,
                "task_status": task_info.get("status", "unknown"),
                "progress": task_info.get("progress", 0),
                "video_url": task_info.get("video_url", ""),
                "error": task_info.get("error"),
                "seconds": task_info.get("seconds"),
                "size": task_info.get("size")
            }

            if task_info.get("status") == "completed" and task_info.get("video_url"):
                try:
                    video_path = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)),
                        "uploads", "videos",
                        task_info["video_url"].lstrip("/uploads/videos/")
                    )
                    if os.path.exists(video_path):
                        size_bytes = os.path.getsize(video_path)
                        result["size"] = f"{size_bytes / (1024*1024):.1f}MB"
                        result["seconds"] = task_info.get("seconds", "未知")
                except:
                    pass

            return result
        else:
            return {"code": "error", "message": "无法获取视频状态"}

    except Exception as e:
        logger.error(f"Video status error: {e}")
        return {"code": "error", "message": f"获取状态失败: {str(e)}"}


@router.post("/optimize-prompt")
async def optimize_prompt(request: Request, managers: dict = Depends(get_managers)):
    """随机选择一个文本模型优化视频提示词"""
    model_manager = managers["model_manager"]
    try:
        body = await request.json()
        prompt = body.get("prompt", "")

        if not prompt:
            return {"code": "error", "message": "提示词不能为空"}

        models = model_manager.get_all()
        text_models = [m for m in models if m.api_key and m.enabled and m.model_type == "text"]

        if not text_models:
            return {"code": "error", "message": "没有可用的文本模型"}

        selected_model = random.choice(text_models)
        logger.info(f"选择模型优化提示词: {selected_model.name} ({selected_model.model_name})")

        adapter = create_llm_adapter(selected_model)
        if not adapter:
            return {"code": "error", "message": f"无法为模型 {selected_model.name} 创建适配器"}

        system_prompt = """你是一个专业的视频提示词优化专家。请帮助用户优化他们的视频生成提示词，使其更加详细、精美和生动。

优化要求：
1. 保持原始意图和主题
2. 添加丰富的视觉细节描述（光线、色彩、氛围、运动等）
3. 使用更具表现力的语言
4. 保持提示词简洁但有画面感
5. 如果原始提示词很简单，适当扩展但不要过度

请直接返回优化后的提示词，不要添加额外的解释或说明。"""

        response = adapter.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请优化这个视频提示词：{prompt}"}
            ],
            temperature=0.7,
            max_tokens=500
        )

        optimized_prompt = response.content.strip()

        return {
            "code": "success",
            "original_prompt": prompt,
            "optimized_prompt": optimized_prompt,
            "model_used": f"{selected_model.name} ({selected_model.model_name})"
        }

    except Exception as e:
        logger.error(f"提示词优化失败: {e}")
        return {"code": "error", "message": f"优化失败: {str(e)}"}
