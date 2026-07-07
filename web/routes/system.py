import os
import json
import random
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import PlainTextResponse, StreamingResponse
from utils.logger import logger
from web.schemas import SettingsUpdate
from engine.agent_worker import create_llm_adapter
from engine.iteration_controller import IterationController

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


def get_state(request: Request):
    return request.app.state


@router.get("/api/version")
async def get_version_api(state=Depends(get_state)):
    """获取应用版本号"""
    return {"version": state.app_version}


@router.get("/api/settings")
async def get_settings(state=Depends(get_state)):
    """获取当前设置"""
    return state.settings


@router.put("/api/settings")
async def update_settings(new_settings: SettingsUpdate, state=Depends(get_state), managers: dict = Depends(get_managers)):
    """更新设置"""
    settings = state.settings
    settings["iterations"] = new_settings.iterations
    settings["enable_search"] = new_settings.enable_search
    settings["max_search_per_iter"] = new_settings.max_search_per_iter
    settings["default_log_level"] = new_settings.default_log_level

    controller = IterationController(
        agent_manager=managers["agent_manager"],
        model_manager=managers["model_manager"],
        log_manager=managers["log_manager"],
        search_manager=managers["search_manager"] if settings["enable_search"] else None,
        iterations=settings["iterations"]
    )
    state.controller = controller

    return {"status": "success", "message": "设置更新成功"}


@router.get("/api/system_info")
async def get_system_info(state=Depends(get_state), managers: dict = Depends(get_managers)):
    """获取系统信息"""
    return {
        "models_count": len(managers["model_manager"].get_all()),
        "agents_count": len(managers["agent_manager"].get_all()),
        "search_engines_count": len(managers["search_manager"].get_all()),
        "attachments_count": len(managers["attachment_manager"].get_attachments()),
        "processing_status": state.processing_status
    }


@router.get("/api/yijing/shake")
async def yijing_shake(content: str = None):
    """执行一次完整摇卦"""
    try:
        from yijing import YijingDivination
        result = YijingDivination.divinate()
        data = result.to_dict()
        if content:
            data['content'] = content
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Yijing divination error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/api/yijing/hexagrams")
async def get_all_hexagrams():
    """获取所有六十四卦数据"""
    from yijing import LIU_SHI_SI_GUA_DETAILS
    return {"status": "success", "hexagrams": LIU_SHI_SI_GUA_DETAILS}


@router.get("/api/yijing/bagua")
async def get_bagua():
    """获取八卦信息"""
    from yijing import BA_GUA
    return {"status": "success", "bagua": BA_GUA}


@router.get("/api/yijing/hexagram/{name}")
async def get_hexagram_by_name(name: str):
    """根据卦名获取详细信息"""
    from yijing import LIU_SHI_SI_GUA_DETAILS, YAO_TEXTS
    if name in LIU_SHI_SI_GUA_DETAILS:
        hexagram = LIU_SHI_SI_GUA_DETAILS[name]
        yao_texts = YAO_TEXTS.get(name, {})
        return {
            "status": "success",
            "hexagram": hexagram,
            "yao_texts": {k: v for k, v in yao_texts.items() if isinstance(k, int)}
        }
    return {"status": "error", "message": "卦象不存在"}


async def _generate_yijing_explain(content: str, original: dict, changed: dict, yao_results: list, change_count: int, change_yao_positions: list, managers: dict):
    """生成AI解卦内容（公共逻辑）"""
    async def generate():
        try:
            configured_models = [m for m in managers["model_manager"].get_all() if m.api_key and m.enabled]
            if not configured_models:
                yield f"data: {{\"status\": \"error\", \"message\": \"请先配置至少一个模型的API密钥\"}}\n\n"
                return

            model = random.choice(configured_models)
            adapter = create_llm_adapter(model)
            if not adapter:
                yield f"data: {{\"status\": \"error\", \"message\": \"无法创建模型适配器\"}}\n\n"
                return

            yao_desc = "\n".join([
                f"  第{y['position']}爻（{y['name']}）：{y['type']}({y['value']}) - {'阳爻' if y['is_yang'] else '阴爻'}{' - 变爻' if y['is_change'] else ''}"
                for y in yao_results
            ])

            prompt = f"""你是一位精通周易的国学大师，请根据以下卦象信息为求测者解卦。

【求测内容】
{content if content else '（未填写）'}

【本卦】
卦名：{original.get('full_name', '')}
卦序：第{original.get('number', '')}卦
卦辞：{original.get('description', '')}

【之卦】{changed.get('full_name', '（无变卦）')}
{changed.get('description', '') if changed else ''}

【六爻详情】（从下往上：初爻→上爻）
{yao_desc}

变爻数：{change_count}
变爻位置：{', '.join([f'第{p}爻' for p in change_yao_positions]) if change_yao_positions else '无'}

请按照以下格式进行解卦：

一、卦象总览
（简要介绍本卦和之卦的基本含义）

二、变爻分析
（分析变爻的具体含义和影响）

三、运势解读
（从事业、财运、感情、健康等方面进行解读）

四、建议与启示
（给求测者的具体建议）

请用通俗易懂的语言，结合卦辞和爻辞进行深入解读，字数不少于500字。"""

            messages = [{"role": "user", "content": prompt}]

            yield f"data: {{\"status\": \"started\", \"model\": \"{model.name}\", \"prompt\": {json.dumps(prompt, ensure_ascii=False)}}}\n\n"

            for chunk in adapter.chat_stream(messages):
                yield f"data: {{\"status\": \"stream\", \"chunk\": {json.dumps(chunk, ensure_ascii=False)}}}\n\n"

            yield f"data: {{\"status\": \"completed\", \"model\": \"{model.name}\", \"prompt\": {json.dumps(prompt, ensure_ascii=False)}}}\n\n"

        except Exception as e:
            logger.error(f"Yijing AI explain error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {{\"status\": \"error\", \"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/yijing/ai-explain")
async def yijing_ai_explain(request: Request, managers: dict = Depends(get_managers)):
    """AI解卦 - 流式返回（POST方式）"""
    try:
        request_data = await request.json()
    except Exception:
        async def error_gen():
            yield f"data: {{\"status\": \"error\", \"message\": \"请求体解析失败\"}}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    return await _generate_yijing_explain(
        content=request_data.get("content", "") or "",
        original=request_data.get("original") or {},
        changed=request_data.get("changed") or {},
        yao_results=request_data.get("yao_results") or [],
        change_count=request_data.get("change_count") or 0,
        change_yao_positions=request_data.get("change_yao_positions") or [],
        managers=managers
    )


@router.get("/api/yijing/ai-explain-stream")
async def yijing_ai_explain_stream(data: str, managers: dict = Depends(get_managers)):
    """AI解卦 - SSE流式返回（GET方式，供EventSource使用）"""
    try:
        request_data = json.loads(data)
    except Exception as e:
        async def error_gen():
            yield f"data: {{\"status\": \"error\", \"message\": \"参数解析失败\"}}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    return await _generate_yijing_explain(
        content=request_data.get("content", ""),
        original=request_data.get("original", {}),
        changed=request_data.get("changed", {}),
        yao_results=request_data.get("yao_results", []),
        change_count=request_data.get("change_count", 0),
        change_yao_positions=request_data.get("change_yao_positions", []),
        managers=managers
    )


@router.get("/api/logs")
async def get_logs(state=Depends(get_state)):
    """获取处理日志"""
    return {"logs": state.processing_log}


@router.post("/api/logs/export")
async def export_logs(state=Depends(get_state)):
    """导出日志到浏览器下载"""
    if not state.processing_log:
        return {"status": "error", "message": "没有日志可导出"}

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs_export_{timestamp}.txt"
        content = "\n".join(state.processing_log)

        headers = {
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Content-Type": "text/plain; charset=utf-8"
        }

        return PlainTextResponse(content, headers=headers)
    except Exception as e:
        return {"status": "error", "message": f"导出失败: {str(e)}"}


@router.post("/api/logs/clear")
async def clear_logs(state=Depends(get_state)):
    """清空日志"""
    state.processing_log.clear()
    return {"status": "success", "message": "日志已清空"}


@router.get("/api/model_calls")
async def get_model_calls(limit: int = 20):
    """获取模型调用日志"""
    from llm.model_call_logger import model_call_logger
    logs = model_call_logger.get_logs(limit)
    return {"logs": logs}


@router.get("/api/model_calls/{log_id}")
async def get_model_call(log_id: str):
    """获取单个模型调用日志详情"""
    from llm.model_call_logger import model_call_logger
    log = model_call_logger.get_log_by_id(log_id)
    if log:
        return {"log": log}
    return {"status": "error", "message": "日志不存在"}


@router.delete("/api/model_calls")
async def clear_model_calls():
    """清空模型调用日志"""
    from llm.model_call_logger import model_call_logger
    model_call_logger.clear_logs()
    return {"status": "success", "message": "模型调用日志已清空"}


@router.post("/api/save")
async def save_document(content: str = Form(...), filename: str = Form(...)):
    """保存文档"""
    try:
        if not filename.endswith('.md'):
            filename += '.md'
        filepath = os.path.join('dist/logs/outputs', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"status": "success", "message": f"文档已保存为 {filename}"}
    except Exception as e:
        return {"status": "error", "message": f"保存失败: {str(e)}"}


@router.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_config():
    return {}
