import asyncio
import json
import os
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from utils.logger import logger

router = APIRouter()


@router.get("/ai-chat/messages")
async def ai_chat_get_messages():
    """获取聊天消息"""
    try:
        from ai_chat_manager import ai_chat_manager
        messages = ai_chat_manager.get_messages()
        return {"status": "success", "data": messages}
    except Exception as e:
        logger.error(f"AI chat get messages error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/ai-chat/upload-file")
async def ai_chat_upload_file(file: UploadFile = File(...)):
    """上传供AI聊天讨论的文件，解析为纯文本返回。

    支持 .txt / .doc / .docx / .pdf / .md。前端拿到 file_text 后随
    /ws/ai-chat 的 start 动作一起发送。
    """
    try:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in {".txt", ".doc", ".docx", ".pdf", ".md"}:
            return {"status": "error",
                    "message": f"不支持的文件类型: {ext or '未知'}（仅支持 txt/doc/docx/pdf/md）"}

        upload_dir = "uploads/ai_chat"
        os.makedirs(upload_dir, exist_ok=True)
        # 防止文件名冲突/路径穿越：加时间戳前缀，仅保留 basename
        safe_name = os.path.basename(file.filename)
        filepath = os.path.join(upload_dir, f"{int(asyncio.get_event_loop().time())}_{safe_name}")

        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        # 用一次性附件实例解析（CPU/IO 密集，丢线程池）；
        # 不复用全局 attachment_manager，避免把文件带入"龙虾Claw"的附件列表
        from attachment.attachment_manager import AttachmentManager
        manager = AttachmentManager()
        att = await asyncio.to_thread(manager.add_attachment, filepath)

        if att is None or not (att.content or "").strip():
            # 解析失败，清理临时文件
            try:
                os.remove(filepath)
            except OSError:
                pass
            return {"status": "error",
                    "message": "文件内容解析失败，请确认文件可读且格式正确"}

        return {
            "status": "success",
            "data": {
                "file_name": att.filename,
                "file_text": att.content,
            },
        }
    except Exception as e:
        logger.error(f"AI chat upload file error: {e}", exc_info=True)
        return {"status": "error", "message": f"上传失败: {str(e)}"}


@router.post("/ai-chat/start")
async def ai_chat_start(request: Request):
    """启动聊天"""
    try:
        request_data = await request.json()
        theme = request_data.get("theme", "")
        file_text = request_data.get("file_text", "")
        file_name = request_data.get("file_name", "")
        from ai_chat_manager import ai_chat_manager
        success = await ai_chat_manager.start_chat(theme, file_text, file_name)
        if success:
            return {"status": "success", "data": {"theme": ai_chat_manager.current_theme}}
        else:
            return {"status": "error", "message": "启动聊天失败，请确保至少添加2个角色"}
    except Exception as e:
        logger.error(f"AI chat start error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/ai-chat/stop")
async def ai_chat_stop():
    """停止聊天"""
    try:
        from ai_chat_manager import ai_chat_manager
        await ai_chat_manager.stop_chat()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"AI chat stop error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/ai-chat/status")
async def ai_chat_status():
    """获取聊天状态"""
    try:
        from ai_chat_manager import ai_chat_manager
        status = ai_chat_manager.get_status()
        return {"status": "success", "data": status}
    except Exception as e:
        logger.error(f"AI chat status error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/ai-chat/generate-theme")
async def ai_chat_generate_theme():
    """生成随机聊天主题"""
    try:
        from ai_chat_manager import ai_chat_manager
        theme = await ai_chat_manager.generate_theme()
        return {"status": "success", "data": {"theme": theme}}
    except Exception as e:
        logger.error(f"AI chat generate theme error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/ai-chat/events")
async def ai_chat_events(request: Request):
    """SSE事件流，实时推送聊天消息"""
    sse_asyncio = asyncio
    from ai_chat_manager import ai_chat_manager

    event_queue = sse_asyncio.Queue()

    async def callback(event_type, data):
        await event_queue.put({"event": event_type, "data": data})

    ai_chat_manager.add_callback(callback)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event_data = await sse_asyncio.wait_for(event_queue.get(), timeout=0.5)
                    message = f"data: {json.dumps(event_data)}\n\n"
                    yield message
                except sse_asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            ai_chat_manager.remove_callback(callback)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/ai-chat/history")
async def ai_chat_get_history(limit: int = 50):
    """获取聊天记录列表"""
    try:
        from ai_chat_manager import ai_chat_manager
        history = ai_chat_manager.get_history_list(limit)
        return {"status": "success", "data": history}
    except Exception as e:
        logger.error(f"AI chat get history error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/ai-chat/history/{session_id}")
async def ai_chat_get_history_detail(session_id: str):
    """获取单条聊天记录的详细信息"""
    try:
        from ai_chat_manager import ai_chat_manager
        detail = ai_chat_manager.get_history_detail(session_id)
        if detail:
            return {"status": "success", "data": detail}
        else:
            return {"status": "error", "message": "聊天记录不存在"}
    except Exception as e:
        logger.error(f"AI chat get history detail error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/ai-chat/history/delete")
async def ai_chat_delete_history(request: Request):
    """删除某条聊天记录"""
    try:
        request_data = await request.json()
        session_id = request_data.get("session_id")
        if not session_id:
            return {"status": "error", "message": "缺少session_id"}

        from ai_chat_manager import ai_chat_manager
        if ai_chat_manager.delete_history(session_id):
            return {"status": "success", "message": "删除成功"}
        else:
            return {"status": "error", "message": "删除失败"}
    except Exception as e:
        logger.error(f"AI chat delete history error: {e}")
        return {"status": "error", "message": str(e)}
