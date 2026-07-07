from fastapi import APIRouter, Request, Depends
from utils.logger import logger
from web.schemas import ModelConfigItem
from models.model_config import ModelConfig
from engine.agent_worker import create_llm_adapter, create_image_adapter

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


@router.get("/models")
async def get_models(managers: dict = Depends(get_managers)):
    """获取所有模型配置"""
    model_manager = managers["model_manager"]
    return [m.to_dict() for m in model_manager.get_all()]


@router.post("/models")
async def create_model(config: ModelConfigItem, managers: dict = Depends(get_managers)):
    """创建新模型"""
    model_manager = managers["model_manager"]
    try:
        model = ModelConfig(
            name=config.name,
            api_type=config.api_type,
            model_type=config.model_type,
            api_url=config.api_url,
            api_key=config.api_key,
            model_name=config.model_name,
            enabled=config.enabled
        )
        model_manager.add(model)
        return {"status": "success", "message": "模型创建成功"}
    except Exception as e:
        logger.error(f"Error creating model: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"创建失败: {str(e)}"}


@router.put("/models/{model_id}")
async def update_model(model_id: str, config: ModelConfigItem, managers: dict = Depends(get_managers)):
    """更新模型配置"""
    model_manager = managers["model_manager"]
    model = ModelConfig(
        id=model_id,
        name=config.name,
        api_type=config.api_type,
        model_type=config.model_type,
        api_url=config.api_url,
        api_key=config.api_key,
        model_name=config.model_name,
        enabled=config.enabled
    )
    model_manager.update(model)
    return {"status": "success", "message": "模型更新成功"}


@router.delete("/models/{model_id}")
async def delete_model(model_id: str, managers: dict = Depends(get_managers)):
    """删除模型"""
    model_manager = managers["model_manager"]
    model_manager.delete(model_id)
    return {"status": "success", "message": "模型删除成功"}


@router.post("/models/{model_id}/test")
async def test_model(model_id: str, managers: dict = Depends(get_managers)):
    """测试模型连通性"""
    model_manager = managers["model_manager"]
    model = model_manager.get(model_id)
    if not model:
        return {"status": "error", "message": "模型不存在"}

    try:
        if model.model_type == "image":
            adapter = create_image_adapter(model)
            if not adapter:
                return {"status": "error", "message": "无法创建文生图适配器"}

            test_prompt = "A beautiful landscape with mountains and river, digital art style"
            response = adapter.generate(test_prompt, n=1, size="256x256")

            if response.success:
                return {"status": "success", "message": "连接成功", "image_url": response.image_url}
            else:
                return {"status": "error", "message": f"测试失败: {response.error}"}
        else:
            adapter = create_llm_adapter(model)
            if not adapter:
                return {"status": "error", "message": "无法创建适配器"}

            test_messages = [{"role": "user", "content": "Hi, please respond with 'OK' if you can read this."}]
            response = adapter.chat(test_messages, max_tokens=10)

            if response.content and "OK" in response.content:
                return {"status": "success", "message": "连接成功"}
            else:
                return {"status": "error", "message": f"响应异常: {response.content}"}
    except Exception as e:
        return {"status": "error", "message": f"连接失败: {str(e)}"}


@router.get("/image-models")
async def get_image_models(managers: dict = Depends(get_managers)):
    """获取所有文生图模型"""
    model_manager = managers["model_manager"]
    image_models = [m.to_dict() for m in model_manager.get_all() if m.model_type == "image"]
    return image_models


@router.get("/video-models")
async def get_video_models(managers: dict = Depends(get_managers)):
    """获取所有文生视频模型"""
    model_manager = managers["model_manager"]
    video_models = [m.to_dict() for m in model_manager.get_all() if m.model_type == "video"]
    return video_models
