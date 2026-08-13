import os
import json
import random
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import PlainTextResponse, StreamingResponse, Response
from utils.logger import logger

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


def generate_yijing_markdown(data):
    content = data.get("content", "")
    date = data.get("date", "")
    original = data.get("original_hexagram", {})
    changed = data.get("changed_hexagram", None)
    yao_results = data.get("yao_results", [])
    change_count = data.get("change_count", 0)
    solution_text = data.get("solution_text", "")
    ai_solution = data.get("ai_solution", "")

    lines = []

    lines.append("# 周易卜卦记录")
    lines.append("")
    lines.append(f"## {content}")
    lines.append("")
    lines.append(f"> 占卜时间：{date}")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 摇卦过程")
    lines.append("")
    lines.append("| 爻位 | 爻名 | 铜钱结果 | 数值 | 类型 | 是否变爻 |")
    lines.append("| :---: | :--- | :--- | :--- | :--- | :--- |")
    sorted_yao = sorted(yao_results, key=lambda y: y.get("position", 0))
    for yao in sorted_yao:
        position = yao.get("position", "")
        name = yao.get("name", "")
        coin_result = yao.get("coin_result", "")
        value = yao.get("value", "")
        yao_type = yao.get("type", "")
        is_change = yao.get("is_change", False)
        change_str = "✅ 变爻" if is_change else "-"
        lines.append(f"| {position} | {name} | {coin_result} | {value} | {yao_type} | {change_str} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 本卦")
    lines.append("")
    full_name = original.get("full_name", "")
    number = original.get("number", "")
    description = original.get("description", "")
    lines.append(f"### {full_name}（第{number}卦）")
    lines.append("")
    lines.append(f"> {description}")
    lines.append("")

    if changed is not None:
        lines.append("---")
        lines.append("")
        lines.append("## 之卦")
        lines.append("")
        changed_full_name = changed.get("full_name", "")
        changed_number = changed.get("number", "")
        changed_description = changed.get("description", "")
        lines.append(f"### {changed_full_name}（第{changed_number}卦）")
        lines.append("")
        lines.append(f"> {changed_description}")
        lines.append("")
        lines.append(f"> 变爻数量：{change_count}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 解卦参考")
    lines.append("")
    if solution_text:
        for sol_line in solution_text.splitlines():
            lines.append(f"> {sol_line}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## AI解卦")
    lines.append("")
    if ai_solution:
        for ai_line in ai_solution.splitlines():
            lines.append(ai_line)
    lines.append("")

    return "\n".join(lines)


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


@router.post("/api/yijing/export")
async def export_yijing_result(request: Request):
    """导出卜卦结果为Markdown文件"""
    try:
        data = await request.json()
        
        original = data.get("original_hexagram", {})
        yao_results = data.get("yao_results", [])
        ai_solution = data.get("ai_solution", "")
        
        if not original or not yao_results:
            return Response(
                content=json.dumps({"status": "error", "message": "缺少必需的卜卦数据"}, ensure_ascii=False),
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        if not ai_solution:
            return Response(
                content=json.dumps({"status": "error", "message": "请先完成AI解卦后再导出"}, ensure_ascii=False),
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        md_content = generate_yijing_markdown(data)
        
        original_name = original.get("full_name", "卦象")
        date_str = datetime.now().strftime("%Y%m%d")
        safe_original_name = "".join(c for c in original_name if c not in '\\/:*?"<>|')
        filename = f"卜卦_{date_str}_{safe_original_name}.md"
        
        from urllib.parse import quote
        encoded_filename = quote(filename, safe="")
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
        
        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers=headers
        )
        
    except Exception as e:
        logger.error(f"Export yijing result error: {e}")
        return Response(
            content=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.get("/api/yijing/history/{session_id}/export")
async def export_yijing_history(session_id: str):
    """从历史记录导出卜卦结果为Markdown文件"""
    try:
        filepath = os.path.join(YIJING_HISTORY_DIR, f"{session_id}.json")
        if not os.path.exists(filepath):
            return Response(
                content=json.dumps({"status": "error", "message": "记录不存在"}, ensure_ascii=False),
                status_code=404,
                media_type="application/json; charset=utf-8"
            )
        
        with open(filepath, "r", encoding="utf-8") as f:
            record = json.load(f)
        
        if not record.get("ai_solution"):
            return Response(
                content=json.dumps({"status": "error", "message": "该记录没有AI解卦数据，无法导出"}, ensure_ascii=False),
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        md_content = generate_yijing_markdown(record)
        
        original = record.get("original_hexagram", {})
        original_name = original.get("full_name", "卦象")
        record_date = record.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        date_str = record_date.replace("-", "").replace(" ", "").replace(":", "")[:8]
        safe_original_name = "".join(c for c in original_name if c not in '\\/:*?"<>|')
        filename = f"卜卦_{date_str}_{safe_original_name}.md"
        
        from urllib.parse import quote
        encoded_filename = quote(filename, safe="")
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
        
        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers=headers
        )
        
    except Exception as e:
        logger.error(f"Export yijing history error: {e}")
        return Response(
            content=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


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
    
    # 使用get_all_logs获取所有日志（包括历史文件）
    logs = model_call_logger.get_all_logs()
    
    if start_date or end_date:
        filtered_logs = []
        for log in logs:
            try:
                log_date = datetime.fromisoformat(log["timestamp"]).date()
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
            except:
                pass
        logs = filtered_logs
    
    if not logs:
        return {
            "total_calls": 0,
            "total_tokens": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_duration": 0,
            "average_duration": 0,
            "average_tokens_per_second": 0,
            "success_rate": 0,
            "total_errors": 0,
            "models": {},
            "daily_stats": []
        }
    
    model_stats = {}
    daily_stats = {}
    total_errors = 0
    
    for log in logs:
        date_str = datetime.fromisoformat(log["timestamp"]).strftime("%Y-%m-%d")
        
        if log.get("error"):
            total_errors += 1
        
        model_name = log.get("model_name", "unknown")
        if model_name not in model_stats:
            model_stats[model_name] = {
                "calls": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "duration": 0,
                "errors": 0,
                "tokens_per_second": 0
            }
        
        model_stats[model_name]["calls"] += 1
        model_stats[model_name]["total_tokens"] += log.get("total_tokens", 0)
        model_stats[model_name]["prompt_tokens"] += log.get("prompt_tokens", 0)
        model_stats[model_name]["completion_tokens"] += log.get("completion_tokens", 0)
        model_stats[model_name]["duration"] += log.get("duration", 0)
        model_stats[model_name]["tokens_per_second"] += log.get("tokens_per_second", 0)
        if log.get("error"):
            model_stats[model_name]["errors"] += 1
        
        if date_str not in daily_stats:
            daily_stats[date_str] = {
                "date": date_str,
                "calls": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "duration": 0,
                "errors": 0
            }
        
        daily_stats[date_str]["calls"] += 1
        daily_stats[date_str]["total_tokens"] += log.get("total_tokens", 0)
        daily_stats[date_str]["prompt_tokens"] += log.get("prompt_tokens", 0)
        daily_stats[date_str]["completion_tokens"] += log.get("completion_tokens", 0)
        daily_stats[date_str]["duration"] += log.get("duration", 0)
        if log.get("error"):
            daily_stats[date_str]["errors"] += 1
    
    total_tokens = sum(log.get("total_tokens", 0) for log in logs)
    total_prompt_tokens = sum(log.get("prompt_tokens", 0) for log in logs)
    total_completion_tokens = sum(log.get("completion_tokens", 0) for log in logs)
    total_duration = sum(log.get("duration", 0) for log in logs)
    total_tokens_per_second = sum(log.get("tokens_per_second", 0) for log in logs)
    
    # 计算每个模型的平均指标
    for model_name, stats in model_stats.items():
        calls = stats["calls"]
        if calls > 0:
            stats["average_duration"] = round(stats["duration"] / calls, 2)
            stats["average_tokens_per_second"] = round(stats["tokens_per_second"] / calls, 2)
            stats["success_rate"] = round(((calls - stats["errors"]) / calls) * 100, 2)
        else:
            stats["average_duration"] = 0
            stats["average_tokens_per_second"] = 0
            stats["success_rate"] = 0
    
    total_calls = len(logs)
    
    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_duration": round(total_duration, 2),
        "average_duration": round(total_duration / total_calls, 2),
        "average_tokens_per_second": round(total_tokens_per_second / total_calls, 2),
        "success_rate": round(((total_calls - total_errors) / total_calls) * 100, 2),
        "total_errors": total_errors,
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
