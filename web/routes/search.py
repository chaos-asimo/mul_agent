from fastapi import APIRouter, Request, Depends, Form
from utils.logger import logger
from web.schemas import SearchEngineConfigItem
from search.search_config import SearchEngineConfig

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


@router.get("/search_engines")
async def get_search_engines(managers: dict = Depends(get_managers)):
    """获取所有搜索引擎配置"""
    search_manager = managers["search_manager"]
    return [s.to_dict() for s in search_manager.get_all()]


@router.post("/search_engines")
async def create_search_engine(config: SearchEngineConfigItem, managers: dict = Depends(get_managers)):
    """创建新搜索引擎"""
    search_manager = managers["search_manager"]
    engine = SearchEngineConfig(
        name=config.name,
        adapter_type=config.adapter_type,
        api_key=config.api_key,
        api_url=config.api_url,
        enabled=config.enabled
    )
    search_manager.add(engine)
    return {"status": "success", "message": "搜索引擎创建成功"}


@router.put("/search_engines/{engine_id}")
async def update_search_engine(engine_id: str, config: SearchEngineConfigItem, managers: dict = Depends(get_managers)):
    """更新搜索引擎配置"""
    search_manager = managers["search_manager"]
    engine = SearchEngineConfig(
        id=engine_id,
        name=config.name,
        adapter_type=config.adapter_type,
        api_key=config.api_key,
        api_url=config.api_url,
        enabled=config.enabled
    )
    search_manager.update(engine)
    return {"status": "success", "message": "搜索引擎更新成功"}


@router.delete("/search_engines/{engine_id}")
async def delete_search_engine(engine_id: str, managers: dict = Depends(get_managers)):
    """删除搜索引擎"""
    search_manager = managers["search_manager"]
    search_manager.delete(engine_id)
    return {"status": "success", "message": "搜索引擎删除成功"}


@router.post("/search_test")
async def test_search(query: str = Form(...), managers: dict = Depends(get_managers)):
    """测试搜索功能"""
    search_manager = managers["search_manager"]
    if not query.strip():
        return {"status": "error", "message": "请输入搜索关键词"}

    try:
        results = await search_manager.search(query, num_results=3)
        if results:
            search_results = []
            for i, result in enumerate(results):
                search_results.append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
                })
            return {"status": "success", "message": "搜索成功", "results": search_results}
        else:
            return {"status": "warning", "message": "未找到搜索结果", "results": []}
    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}


@router.post("/search/quick")
async def quick_search(request: dict, managers: dict = Depends(get_managers)):
    """
    快速搜索API - 随时按需调用

    Request body:
        query: 搜索关键词
        num_results: 返回数量（默认5条）
    """
    from search.search_tool import quick_search

    search_manager = managers["search_manager"]
    query = request.get("query", "")
    num_results = request.get("num_results", 5)

    if not query.strip():
        return {"status": "error", "message": "请输入搜索关键词"}

    try:
        tavily_key = ""
        for engine in search_manager.get_all():
            if engine.adapter_type == "tavily" and engine.enabled and engine.api_key:
                tavily_key = engine.api_key
                break

        if not tavily_key:
            return {"status": "warning", "message": "未配置Tavily搜索，请先在设置中添加搜索引擎", "results": []}

        results = await quick_search(query, tavily_key, num_results)

        return {
            "status": "success",
            "message": f"搜索成功，获取到 {len(results)} 条结果",
            "results": results
        }
    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}


@router.post("/search/context")
async def search_for_context(request: dict, managers: dict = Depends(get_managers)):
    """
    搜索并返回格式化上下文 - 随时按需调用

    Request body:
        query: 搜索关键词
        num_results: 返回数量（默认3条）
    """
    from search.search_tool import quick_search_context

    search_manager = managers["search_manager"]
    query = request.get("query", "")
    num_results = request.get("num_results", 3)

    if not query.strip():
        return {"status": "error", "message": "请输入搜索关键词"}

    try:
        tavily_key = ""
        for engine in search_manager.get_all():
            if engine.adapter_type == "tavily" and engine.enabled and engine.api_key:
                tavily_key = engine.api_key
                break

        if not tavily_key:
            return {"status": "warning", "message": "未配置Tavily搜索", "context": ""}

        context = await quick_search_context(query, tavily_key, num_results)

        return {
            "status": "success",
            "message": "搜索完成",
            "context": context
        }
    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}
