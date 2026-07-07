from fastapi import APIRouter, Request, Depends
from utils.logger import logger
from web.schemas import AgentConfigItem
from agents.agent_config import AgentConfig

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


@router.get("/agents")
async def get_agents(managers: dict = Depends(get_managers)):
    """获取所有Agent配置"""
    agent_manager = managers["agent_manager"]
    return [a.to_dict() for a in agent_manager.get_all()]


@router.post("/agents")
async def create_agent(config: AgentConfigItem, managers: dict = Depends(get_managers)):
    """创建新Agent"""
    agent_manager = managers["agent_manager"]
    agent = AgentConfig(
        name=config.name,
        role_description=config.role_description,
        model_id=config.model_id,
        enabled=config.enabled,
        order=config.order
    )
    agent_manager.add(agent)
    return {"status": "success", "message": "Agent创建成功"}


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, config: AgentConfigItem, managers: dict = Depends(get_managers)):
    """更新Agent配置"""
    agent_manager = managers["agent_manager"]
    agent = AgentConfig(
        id=agent_id,
        name=config.name,
        role_description=config.role_description,
        model_id=config.model_id,
        enabled=config.enabled,
        order=config.order
    )
    agent_manager.update(agent)
    return {"status": "success", "message": "Agent更新成功"}


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, managers: dict = Depends(get_managers)):
    """删除Agent"""
    agent_manager = managers["agent_manager"]
    agent_manager.delete(agent_id)
    return {"status": "success", "message": "Agent删除成功"}


@router.get("/ai-chat/agents")
async def ai_chat_get_agents(refresh: bool = False):
    """获取可用的agent列表"""
    try:
        from ai_chat_manager import ai_chat_manager
        if refresh:
            ai_chat_manager.refresh_agents()
        agents = ai_chat_manager.get_available_agents()
        return {"status": "success", "data": agents}
    except Exception as e:
        logger.error(f"AI chat get agents error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/ai-chat/add-role")
async def ai_chat_add_role(request: Request):
    """添加角色到聊天列表"""
    try:
        request_data = await request.json()
        agent_id = request_data.get("agent_id")
        from ai_chat_manager import ai_chat_manager
        role = ai_chat_manager.add_role(agent_id)
        if role:
            return {"status": "success", "data": role.to_dict()}
        else:
            return {"status": "error", "message": "添加角色失败"}
    except Exception as e:
        logger.error(f"AI chat add role error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/ai-chat/remove-role")
async def ai_chat_remove_role(request: Request):
    """从聊天列表移除角色"""
    try:
        request_data = await request.json()
        agent_id = request_data.get("agent_id")
        from ai_chat_manager import ai_chat_manager
        success = ai_chat_manager.remove_role(agent_id)
        return {"status": "success" if success else "error", "data": {"agent_id": agent_id}}
    except Exception as e:
        logger.error(f"AI chat remove role error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/ai-chat/roles")
async def ai_chat_get_roles():
    """获取当前角色列表"""
    try:
        from ai_chat_manager import ai_chat_manager
        roles = ai_chat_manager.get_roles()
        return {"status": "success", "data": roles}
    except Exception as e:
        logger.error(f"AI chat get roles error: {e}")
        return {"status": "error", "message": str(e)}
