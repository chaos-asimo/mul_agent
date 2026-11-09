from fastapi import APIRouter, Request, Depends
from utils.logger import logger
from web.schemas import ImageGenerateRequest
from engine.agent_worker import create_image_adapter

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


@router.post("/image-generate")
async def generate_image(request: ImageGenerateRequest, managers: dict = Depends(get_managers)):
    """文生图API"""
    model_manager = managers["model_manager"]
    try:
        models = model_manager.get_all()

        if request.model_id:
            model = model_manager.get(request.model_id)
        else:
            image_models = [m for m in models if m.api_key and m.enabled and m.model_type == "image"]
            if not image_models:
                return {"status": "error", "message": "请先配置至少一个文生图模型"}
            model = image_models[0]

        if model.model_type != "image":
            return {"status": "error", "message": "选择的模型不是文生图模型"}

        adapter = create_image_adapter(model)
        if not adapter:
            return {"status": "error", "message": "无法创建文生图适配器"}

        response = adapter.generate(
            prompt=request.prompt,
            n=request.n,
            size=request.size,
            negative_prompt=request.negative_prompt
        )

        if response.success:
            return {
                "status": "success",
                "model": model.name,
                "image_url": response.image_url,
                "image_data": response.image_data.decode('utf-8') if response.image_data else None
            }
        else:
            return {"status": "error", "message": f"生成失败: {response.error}"}

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"生成失败: {str(e)}"}
