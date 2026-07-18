import os
import json
import random
from datetime import datetime
from typing import Optional
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


YIJING_HISTORY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "yijing_history")

@router.post("/api/yijing/save")
async def save_yijing_history(request: Request):
    """保存卜卦结果"""
    try:
        data = await request.json()
        os.makedirs(YIJING_HISTORY_DIR, exist_ok=True)
        
        session_id = str(random.randint(10000000, 99999999))
        record = {
            "session_id": session_id,
            "content": data.get("content", ""),
            "original_hexagram": data.get("original_hexagram", {}),
            "changed_hexagram": data.get("changed_hexagram", None),
            "yao_results": data.get("yao_results", []),
            "change_count": data.get("change_count", 0),
            "change_yao_positions": data.get("change_yao_positions", []),
            "solution_text": data.get("solution_text", ""),
            "ai_solution": data.get("ai_solution", ""),
            "timestamp": datetime.now().timestamp(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        filepath = os.path.join(YIJING_HISTORY_DIR, f"{session_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        
        return {"status": "success", "session_id": session_id}
    except Exception as e:
        logger.error(f"Save yijing history error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/api/yijing/history")
async def get_yijing_history():
    """获取卜卦历史列表"""
    try:
        os.makedirs(YIJING_HISTORY_DIR, exist_ok=True)
        history = []
        
        if not os.path.exists(YIJING_HISTORY_DIR):
            return {"status": "success", "data": []}
        
        files = sorted(os.listdir(YIJING_HISTORY_DIR), key=lambda x: os.path.getmtime(os.path.join(YIJING_HISTORY_DIR, x)), reverse=True)
        
        for filename in files:
            if not filename.endswith(".json"):
                continue
            try:
                filepath = os.path.join(YIJING_HISTORY_DIR, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    record = json.load(f)
                original_name = record["original_hexagram"].get("full_name", "") if record.get("original_hexagram") else ""
                history.append({
                    "session_id": record["session_id"],
                    "content": record["content"],
                    "original_name": original_name,
                    "change_count": record["change_count"],
                    "date": record["date"]
                })
            except Exception as e:
                logger.error(f"Read yijing history error: {e}")
        
        return {"status": "success", "data": history}
    except Exception as e:
        logger.error(f"Get yijing history error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/api/yijing/history/{session_id}")
async def get_yijing_history_detail(session_id: str):
    """获取单个卜卦记录详情"""
    try:
        filepath = os.path.join(YIJING_HISTORY_DIR, f"{session_id}.json")
        if not os.path.exists(filepath):
            return {"status": "error", "message": "记录不存在"}
        
        with open(filepath, "r", encoding="utf-8") as f:
            record = json.load(f)
        
        return {"status": "success", "data": record}
    except Exception as e:
        logger.error(f"Get yijing history detail error: {e}")
        return {"status": "error", "message": str(e)}


@router.delete("/api/yijing/history/{session_id}")
async def delete_yijing_history(session_id: str):
    """删除卜卦历史记录"""
    try:
        filepath = os.path.join(YIJING_HISTORY_DIR, f"{session_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return {"status": "success", "message": "删除成功"}
        return {"status": "error", "message": "记录不存在"}
    except Exception as e:
        logger.error(f"Delete yijing history error: {e}")
        return {"status": "error", "message": str(e)}


def _generate_yijing_explain(content: str, original: dict, changed: dict, yao_results: list, change_count: int, change_yao_positions: list, managers: dict):
    """生成AI解卦内容（公共逻辑）"""
    async def generate():
        import asyncio
        try:
            text_models = [m for m in managers["model_manager"].get_all() if m.api_key and m.enabled and m.model_type == "text"]
            if not text_models:
                yield f"data: {{\"status\": \"error\", \"message\": \"请先配置至少一个文本类型的模型\"}}\n\n"
                return

            model = random.choice(text_models)
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
                if chunk.startswith("{\"__stats__\""):
                    continue
                if chunk.startswith("Error:"):
                    yield f"data: {{\"status\": \"error\", \"message\": {json.dumps(chunk[7:], ensure_ascii=False)}}}\n\n"
                    return
                yield f"data: {{\"status\": \"stream\", \"chunk\": {json.dumps(chunk, ensure_ascii=False)}}}\n\n"
                await asyncio.sleep(0.01)

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

    return _generate_yijing_explain(
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

    return _generate_yijing_explain(
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


@router.get("/api/model_calls/statistics")
async def get_model_call_statistics(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取模型调用统计数据"""
    from llm.model_call_logger import model_call_logger
    from datetime import datetime
    
    logs = model_call_logger.call_logs
    
    if start_date or end_date:
        filtered_logs = []
        for log in logs:
            log_date = log.timestamp.date()
            if start_date:
                try:
                    start = datetime.strptime(start_date, "%Y-%m-%d").date()
                    if log_date < start:
                        continue
                except:
                    pass
            if end_date:
                try:
                    end = datetime.strptime(end_date, "%Y-%m-%d").date()
                    if log_date > end:
                        continue
                except:
                    pass
            filtered_logs.append(log)
        logs = filtered_logs
    
    if not logs:
        return {
            "total_calls": 0,
            "total_tokens": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_duration": 0,
            "models": {},
            "daily_stats": []
        }
    
    model_stats = {}
    daily_stats = {}
    
    for log in logs:
        date_str = log.timestamp.strftime("%Y-%m-%d")
        
        if log.model_name not in model_stats:
            model_stats[log.model_name] = {
                "calls": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "duration": 0
            }
        
        model_stats[log.model_name]["calls"] += 1
        model_stats[log.model_name]["total_tokens"] += log.total_tokens
        model_stats[log.model_name]["prompt_tokens"] += log.prompt_tokens
        model_stats[log.model_name]["completion_tokens"] += log.completion_tokens
        model_stats[log.model_name]["duration"] += log.duration
        
        if date_str not in daily_stats:
            daily_stats[date_str] = {
                "date": date_str,
                "calls": 0,
                "total_tokens": 0
            }
        
        daily_stats[date_str]["calls"] += 1
        daily_stats[date_str]["total_tokens"] += log.total_tokens
    
    total_tokens = sum(log.total_tokens for log in logs)
    total_prompt_tokens = sum(log.prompt_tokens for log in logs)
    total_completion_tokens = sum(log.completion_tokens for log in logs)
    total_duration = sum(log.duration for log in logs)
    
    return {
        "total_calls": len(logs),
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_duration": round(total_duration, 2),
        "models": model_stats,
        "daily_stats": sorted(daily_stats.values(), key=lambda x: x["date"], reverse=True)[:7]
    }


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
