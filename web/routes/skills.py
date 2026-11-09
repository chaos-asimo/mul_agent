from fastapi import APIRouter, Request, Depends
from utils.logger import logger
from skills.skill_config import SkillConfig

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


@router.get("/skills")
async def get_skills(managers: dict = Depends(get_managers)):
    """获取所有Skills"""
    skill_manager = managers["skill_manager"]
    skills = skill_manager.get_all()
    return {"skills": [s.to_dict() for s in skills]}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, managers: dict = Depends(get_managers)):
    """获取单个Skill"""
    skill_manager = managers["skill_manager"]
    skill = skill_manager.get_by_id(skill_id)
    if skill:
        return {"skill": skill.to_dict()}
    return {"error": "Skill不存在"}


@router.post("/skills")
async def create_skill(skill_data: dict, managers: dict = Depends(get_managers)):
    """创建新Skill"""
    skill_manager = managers["skill_manager"]
    skill = SkillConfig.from_dict(skill_data)

    errors = skill_manager.validate_skill(skill)
    if errors:
        return {"status": "error", "message": "配置验证失败", "errors": errors}

    if skill_manager.add(skill):
        return {"status": "success", "message": "Skill创建成功", "skill": skill.to_dict()}
    return {"status": "error", "message": "Skill已存在"}


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, skill_data: dict, managers: dict = Depends(get_managers)):
    """更新Skill"""
    skill_manager = managers["skill_manager"]
    skill = SkillConfig.from_dict(skill_data)
    skill.id = skill_id

    errors = skill_manager.validate_skill(skill)
    if errors:
        return {"status": "error", "message": "配置验证失败", "errors": errors}

    if skill_manager.update(skill):
        return {"status": "success", "message": "Skill更新成功", "skill": skill.to_dict()}
    return {"status": "error", "message": "Skill不存在"}


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, managers: dict = Depends(get_managers)):
    """删除Skill"""
    skill_manager = managers["skill_manager"]
    if skill_manager.delete(skill_id):
        return {"status": "success", "message": "Skill删除成功"}
    return {"status": "error", "message": "Skill不存在"}


@router.post("/skills/{skill_id}/enable")
async def enable_skill(skill_id: str, managers: dict = Depends(get_managers)):
    """启用Skill"""
    skill_manager = managers["skill_manager"]
    if skill_manager.enable(skill_id):
        return {"status": "success", "message": "Skill已启用"}
    return {"status": "error", "message": "Skill不存在"}


@router.post("/skills/{skill_id}/disable")
async def disable_skill(skill_id: str, managers: dict = Depends(get_managers)):
    """禁用Skill"""
    skill_manager = managers["skill_manager"]
    if skill_manager.disable(skill_id):
        return {"status": "success", "message": "Skill已禁用"}
    return {"status": "error", "message": "Skill不存在"}


@router.post("/skills/analyze")
async def analyze_skills(request: dict, managers: dict = Depends(get_managers)):
    """分析输入内容，返回建议调用的Skills"""
    skill_manager = managers["skill_manager"]
    content = request.get("content", "")

    if not content:
        return {"status": "success", "matched_skills": [], "reason": "输入内容为空"}

    enabled_skills = [s for s in skill_manager.get_all() if s.enabled]

    if not enabled_skills:
        return {"status": "success", "matched_skills": [], "reason": "没有启用的Skills"}

    matched = []

    for skill in enabled_skills:
        score = 0
        reasons = []

        name_keywords = skill.name.lower().split()
        content_lower = content.lower()
        for keyword in name_keywords:
            if keyword in content_lower:
                score += 2
                reasons.append(f"名称匹配: {keyword}")

        if skill.description:
            desc_keywords = skill.description.lower().split()
            for keyword in desc_keywords:
                if len(keyword) > 2 and keyword in content_lower:
                    score += 1
                    reasons.append(f"描述匹配: {keyword}")

        if skill.tags:
            for tag in skill.tags:
                if tag.lower() in content_lower:
                    score += 1.5
                    reasons.append(f"标签匹配: {tag}")

        type_keywords = {
            "search": ["搜索", "查找", "查询", "search", "find"],
            "analysis": ["分析", "研究", "研究", "analysis", "analyze"],
            "generation": ["生成", "创建", "编写", "生成", "generate", "create"],
            "transform": ["转换", "翻译", "改写", "transform", "translate"],
            "validation": ["验证", "检查", "测试", "validate", "check", "verify"]
        }

        skill_type_value = skill.skill_type.value if hasattr(skill.skill_type, 'value') else str(skill.skill_type)
        if skill_type_value in type_keywords:
            for keyword in type_keywords[skill_type_value]:
                if keyword in content_lower:
                    score += 1
                    reasons.append(f"类型匹配: {keyword}")

        if score > 0:
            matched.append({
                "skill_id": skill.id,
                "skill_name": skill.name,
                "score": score,
                "reasons": reasons
            })

    matched.sort(key=lambda x: x["score"], reverse=True)
    top_matches = matched[:3]

    return {
        "status": "success",
        "matched_skills": top_matches,
        "reason": f"找到 {len(top_matches)} 个可能的Skill"
    }


@router.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, request: dict, managers: dict = Depends(get_managers)):
    """执行Skill"""
    skill_executor = managers["skill_executor"]
    params = request.get("params", {})
    context = request.get("context", {})

    print(f"[API] execute_skill: skill_id={skill_id}, params={params}")
    print(f"[API] skill_executor.search_manager={skill_executor.search_manager}")
    print(f"[API] adapters={skill_executor.search_manager.adapters if skill_executor.search_manager else None}")

    result = await skill_executor.execute(skill_id, params, context)
    return {"result": result.to_dict()}


@router.post("/skills/chain")
async def execute_skill_chain(request: dict, managers: dict = Depends(get_managers)):
    """执行Skill链"""
    skill_executor = managers["skill_executor"]
    skill_ids = request.get("skill_ids", [])
    params = request.get("params", {})

    results = await skill_executor.execute_chain(skill_ids, params)
    return {"results": [r.to_dict() for r in results]}


@router.get("/skills/history")
async def get_skill_history(limit: int = 50, managers: dict = Depends(get_managers)):
    """获取Skill执行历史"""
    skill_executor = managers["skill_executor"]
    history = skill_executor.get_execution_history(limit)
    return {"history": history}


@router.post("/skills/reset")
async def reset_skills(managers: dict = Depends(get_managers)):
    """重置Skills为默认配置"""
    skill_manager = managers["skill_manager"]
    skill_manager.reset_to_default()
    return {"status": "success", "message": "Skills已重置为默认配置"}
