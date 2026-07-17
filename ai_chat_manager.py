"""AI Chat Manager for multi-agent conversation"""
import asyncio
import json
import os
import uuid
import time
import random
import logging
import re

# 过滤模型思考内容（如 <think>...</think>）
_THINK_BLOCK_RE = re.compile(r'<(think|thinking|reasoning)\b[^>]*>.*?</\1>', re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r'<(think|thinking|reasoning)\b[^>]*>.*', re.DOTALL | re.IGNORECASE)

def strip_thinking(text: str) -> str:
    """Remove thinking/reasoning blocks from model output."""
    text = _THINK_BLOCK_RE.sub('', text)
    text = _THINK_OPEN_RE.sub('', text)
    return text.strip()
from queue import Queue, Empty
from typing import List, Dict, Optional
from starlette.websockets import WebSocketState
from agents import AgentManager
from models import ModelManager
from search import SearchManager
from engine.agent_worker import create_llm_adapter, create_image_adapter, create_video_adapter

logger = logging.getLogger(__name__)


# 历史记录存储路径
BASE_DIR = os.path.dirname(__file__)
HISTORY_DIR = os.path.abspath(os.path.join(BASE_DIR, "data", "ai_chat_history"))


class ChatRole:
    """A role in the chat with bound model"""
    
    def __init__(self, agent_id: str, name: str, role_description: str, model_id: str, model_name: str, model_type: str = "text"):
        self.agent_id = agent_id
        self.name = name
        self.role_description = role_description
        self.model_id = model_id
        self.model_name = model_name
        self.model_type = model_type
        self.adapter = None
    
    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role_description": self.role_description,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "model_type": self.model_type
        }


class ChatMessage:
    """A chat message from a role"""
    
    def __init__(self, role_name: str, content: str, timestamp: float, is_image: bool = False, image_url: str = "", image_data: str = "", image_prompt: str = "", is_video: bool = False, video_url: str = "", video_prompt: str = ""):
        self.role_name = role_name
        self.content = content
        self.timestamp = timestamp
        self.is_image = is_image
        self.image_url = image_url
        self.image_data = image_data
        self.image_prompt = image_prompt
        self.is_video = is_video
        self.video_url = video_url
        self.video_prompt = video_prompt
    
    def to_dict(self) -> Dict:
        return {
            "role_name": self.role_name,
            "content": self.content,
            "timestamp": self.timestamp,
            "is_image": self.is_image,
            "image_url": self.image_url,
            "image_data": self.image_data,
            "image_prompt": self.image_prompt,
            "is_video": self.is_video,
            "video_url": self.video_url,
            "video_prompt": self.video_prompt
        }


class AIChatManager:
    """Manages AI chat sessions with multiple agents"""
    
    MAX_CONTEXT_MESSAGES = 10
    MAX_RESPONSE_LENGTH = 256
    
    def __init__(self):
        self.agent_manager = AgentManager()
        self.model_manager = ModelManager()
        self.search_manager = SearchManager()
        self.roles: List[ChatRole] = []
        self.messages: List[ChatMessage] = []
        self.is_chatting = False
        self.chat_task: Optional[asyncio.Task] = None
        self.current_theme = ""
        self.callbacks = []
        self.websockets = set()
    
    def add_callback(self, callback):
        self.callbacks.append(callback)
    
    def remove_callback(self, callback):
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    async def notify(self, event_type: str, data: Dict):
        for callback in self.callbacks:
            try:
                await callback(event_type, data)
            except:
                pass
        
        for ws in list(self.websockets):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json({"event": event_type, "data": data})
                else:
                    self.websockets.discard(ws)
            except:
                self.websockets.discard(ws)
    
    def add_websocket(self, ws):
        self.websockets.add(ws)
    
    def remove_websocket(self, ws):
        self.websockets.discard(ws)
    
    def get_available_agents(self) -> List[Dict]:
        """Get all available agents"""
        return [a.to_dict() for a in self.agent_manager.get_all()]
    
    def refresh_agents(self):
        """Refresh agents from config file"""
        self.agent_manager.load()
    
    def get_available_models(self) -> List[Dict]:
        """Get all enabled models with API keys"""
        return [m.to_dict() for m in self.model_manager.get_all() if m.api_key and m.enabled]
    
    def bind_model_to_role(self, agent_id: str) -> Optional[Dict]:
        """Bind an available model to an agent"""
        agent = self.agent_manager.get(agent_id)
        if agent and agent.model_id:
            model = self.model_manager.get(agent.model_id)
            if model and model.api_key and model.enabled:
                return model.to_dict()
        
        available_models = [m for m in self.model_manager.get_all() if m.api_key and m.enabled and m.model_type == "text"]
        if not available_models:
            return None
        
        return random.choice(available_models).to_dict()
    
    def add_role(self, agent_id: str) -> Optional[ChatRole]:
        """Add an agent as a chat role"""
        agent = self.agent_manager.get(agent_id)
        if not agent:
            return None
        
        for role in self.roles:
            if role.agent_id == agent_id:
                return None
        
        model_data = self.bind_model_to_role(agent_id)
        if not model_data:
            return None
        
        role = ChatRole(
            agent_id=agent.id,
            name=agent.name,
            role_description=agent.role_description,
            model_id=model_data["id"],
            model_name=model_data["name"],
            model_type=model_data.get("model_type", "text")
        )
        self.roles.append(role)
        return role
    
    def remove_role(self, agent_id: str) -> bool:
        """Remove a role from the chat"""
        for i, role in enumerate(self.roles):
            if role.agent_id == agent_id:
                del self.roles[i]
                return True
        return False
    
    def clear_roles(self):
        """Clear all roles"""
        self.roles = []
    
    def get_roles(self) -> List[Dict]:
        """Get all current roles"""
        return [r.to_dict() for r in self.roles]
    
    def get_messages(self) -> List[Dict]:
        """Get all messages"""
        return [m.to_dict() for m in self.messages]
    
    def save_current_chat(self) -> Optional[str]:
        """保存当前聊天记录到文件"""
        # 确保目录存在
        os.makedirs(HISTORY_DIR, exist_ok=True)
        
        if not self.messages or not self.current_theme:
            logger.warning(f"跳过保存：messages={len(self.messages) if self.messages else 0}, theme={bool(self.current_theme)}")
            return None
        
        session_id = str(uuid.uuid4())[:8]
        chat_record = {
            "session_id": session_id,
            "theme": self.current_theme,
            "roles": [r.to_dict() for r in self.roles],
            "messages": [m.to_dict() for m in self.messages],
            "message_count": len(self.messages),
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        filename = f"{session_id}.json"
        filepath = os.path.join(HISTORY_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(chat_record, f, ensure_ascii=False, indent=2)
        
        logger.info(f"聊天记录已保存: {session_id}, {len(self.messages)}条消息, 主题: {self.current_theme}")
        return session_id
    
    def get_history_list(self, limit: int = 50) -> List[Dict]:
        """获取聊天记录列表（只返回摘要信息）"""
        history = []
        # 确保目录存在
        os.makedirs(HISTORY_DIR, exist_ok=True)
        
        if not os.path.exists(HISTORY_DIR):
            return history
        
        files = sorted(os.listdir(HISTORY_DIR), key=lambda x: os.path.getmtime(os.path.join(HISTORY_DIR, x)), reverse=True)
        
        for filename in files[:limit]:
            if not filename.endswith(".json"):
                continue
            try:
                filepath = os.path.join(HISTORY_DIR, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    record = json.load(f)
                history.append({
                    "session_id": record["session_id"],
                    "theme": record["theme"],
                    "date": record["date"],
                    "message_count": record["message_count"],
                    "role_names": [r["name"] for r in record["roles"][:5]]  # 只取前5个角色
                })
            except Exception as e:
                logger.error(f"读取历史记录失败: {e}")
        
        return history
    
    def get_history_detail(self, session_id: str) -> Optional[Dict]:
        """获取单个聊天的详细信息"""
        filepath = os.path.join(HISTORY_DIR, f"{session_id}.json")
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取聊天记录详情失败: {e}")
            return None
    
    def delete_history(self, session_id: str) -> bool:
        """删除某条聊天记录"""
        filepath = os.path.join(HISTORY_DIR, f"{session_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
    
    async def search_for_info(self, query: str) -> str:
        """Search for information online"""
        try:
            results = await self.search_manager.search(query)
            if results and len(results) > 0:
                info = "\n".join([f"- {r['title']}: {r['snippet'][:100]}" for r in results[:3]])
                return f"搜索到相关信息：\n{info}"
        except Exception as e:
            pass
        return ""
    
    async def generate_response(self, role: ChatRole, context: str, theme: str, search_info: str = "") -> str:
        """Generate a response from a role"""
        full_response = ""
        async for chunk in self.generate_response_stream(role, context, theme, search_info):
            full_response += chunk
        return full_response
    
    async def generate_image_response(self, role: ChatRole, last_message: str, theme: str) -> Dict:
        """Generate an image response from a role with image model"""
        if not role.adapter:
            model = self.model_manager.get(role.model_id)
            if model:
                role.adapter = create_image_adapter(model)
        
        if not role.adapter:
            return {"success": False, "error": "无法连接到文生图模型"}
        
        # 使用上一个角色的发言作为提示词
        image_prompt = last_message if last_message else theme
        
        try:
            response = role.adapter.generate(image_prompt, size="1024x1024")
            
            if response.success:
                return {
                    "success": True,
                    "image_url": response.image_url,
                    "image_data": response.image_data.decode('utf-8') if response.image_data else None,
                    "prompt": image_prompt
                }
            else:
                return {"success": False, "error": response.error}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def generate_video_response(self, role: ChatRole, last_message: str, theme: str) -> Dict:
        """Generate a video response from a role with video model"""
        if not role.adapter:
            model = self.model_manager.get(role.model_id)
            if model:
                role.adapter = create_video_adapter(model)
        
        if not role.adapter:
            return {"success": False, "error": "无法连接到视频生成模型"}
        
        video_prompt = last_message if last_message else theme
        
        try:
            response = role.adapter.generate(video_prompt)
            
            if response.success:
                video_id = response.video_id
                task_id = response.task_id
                
                if video_id:
                    max_retries = 120
                    retry_interval = 5
                    
                    for attempt in range(max_retries):
                        status_result = role.adapter.get_status(video_id)
                        video_status = status_result.get("status", "")
                        progress = status_result.get("progress", 0)
                        
                        if video_status == "completed" and status_result.get("video_url"):
                            return {
                                "success": True,
                                "video_url": status_result["video_url"],
                                "video_id": video_id,
                                "prompt": video_prompt,
                                "status": "completed",
                                "progress": 100
                            }
                        elif video_status in ["queued", "processing", "in_progress"]:
                            await self.notify("message_chunk", {
                                "role_name": role.name,
                                "chunk": f"视频生成中... (进度: {progress}%)",
                                "full_content": f"视频生成中... (视频ID: {video_id}, 进度: {progress}%)"
                            })
                            
                            await asyncio.sleep(retry_interval)
                        else:
                            return {"success": False, "error": status_result.get("error", "视频生成失败")}
                    
                    return {"success": False, "error": f"视频生成超时（已等待{max_retries * retry_interval}秒）"}
                else:
                    return {"success": False, "error": "未返回视频ID"}
            else:
                return {"success": False, "error": response.error}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def generate_response_stream(self, role: ChatRole, context: str, theme: str, search_info: str = ""):
        """Generate a streaming response from a role, yields chunks"""
        if not role.adapter:
            model = self.model_manager.get(role.model_id)
            if model:
                role.adapter = create_llm_adapter(model)
        
        if not role.adapter:
            yield "抱歉，无法连接到模型。"
            return
        
        system_prompt = f"""你现在扮演"{role.name}"的角色。

{role.role_description}

聊天主题：{theme}

当前对话上下文（最近的对话）：
{context}

{search_info}

请针对上一位发言者的内容进行回应，保持对话连贯。
要求：
1. 回答字数控制在256字以内
2. 直接输出回答内容，不需要额外说明
3. 尽量少用或不用emoji表情
4. 保持角色特性和语气一致"""
        
        user_prompt = "请针对以上对话进行回应。"
        
        messages = None
        try:
            messages = role.adapter.create_prompt(system_prompt, user_prompt, [])
        except Exception as e:
            yield f"发言失败：{str(e)[:50]}"
            return
        
        raw_content = ""
        displayed_content = ""
        chunk_queue = Queue()
        worker_started = False
        
        try:
            def stream_worker():
                try:
                    for chunk in role.adapter.chat_stream(messages):
                        if isinstance(chunk, str) and chunk.startswith('{"__stats__"'):
                            continue
                        chunk_queue.put(chunk)
                except Exception as e:
                    chunk_queue.put(f"Error: {str(e)}")
                finally:
                    chunk_queue.put(None)
            
            asyncio.get_event_loop().run_in_executor(None, stream_worker)
            worker_started = True
            
            while True:
                try:
                    chunk = await asyncio.get_event_loop().run_in_executor(None, chunk_queue.get, True, 0.1)
                    if chunk is None:
                        break
                    if chunk.startswith("Error:"):
                        yield chunk
                        return
                    raw_content += chunk
                    filtered_content = strip_thinking(raw_content)
                    delta = filtered_content[len(displayed_content):]
                    if delta:
                        displayed_content = filtered_content
                        yield delta
                except asyncio.TimeoutError:
                    continue
                except Empty:
                    continue
                except asyncio.CancelledError:
                    chunk_queue.put(None)
                    raise
                except GeneratorExit:
                    chunk_queue.put(None)
                    return
        
        except GeneratorExit:
            chunk_queue.put(None)
            return
        except Exception as e:
            yield f"发言失败：{str(e)[:50]}"
    
    async def generate_theme(self) -> str:
        """Generate a random chat theme"""
        themes = [
            "讨论人工智能对未来工作的影响",
            "探讨如何平衡工作与生活",
            "分析当前的教育改革趋势",
            "讨论环境保护与经济发展的关系",
            "分享对未来科技发展的展望",
            "探讨社交媒体对人际关系的影响",
            "分析远程办公的利弊",
            "讨论如何提升团队协作效率"
        ]
        return random.choice(themes)
    
    async def chat_loop(self, theme: str):
        """Main chat loop"""
        self.current_theme = theme
        self.messages = []
        
        await self.notify("theme", {"theme": theme})
        
        round_count = 0
        max_rounds = 20
        message_index = 0
        last_active_time = asyncio.get_event_loop().time()
        
        try:
            while self.is_chatting and round_count < max_rounds:
                for role in self.roles:
                    if not self.is_chatting:
                        break
                    
                    message_index += 1
                    
                    await self.notify("typing", {"role_name": role.name})
                    last_active_time = asyncio.get_event_loop().time()
                    
                    recent_messages = self.messages[-self.MAX_CONTEXT_MESSAGES:]
                    context = "\n".join([f"{m.role_name}: {m.content}" for m in recent_messages])
                    
                    if not context:
                        context = f"聊天开始，主题：{theme}"
                    
                    if role.model_type == "image":
                        # 获取上一个角色的发言作为提示词
                        last_message = ""
                        if self.messages:
                            last_message = self.messages[-1].content
                        
                        image_result = await self.generate_image_response(role, last_message, theme)
                        
                        if image_result["success"]:
                            image_url = image_result.get("image_url", "")
                            image_data = image_result.get("image_data", "")
                            prompt = image_result.get("prompt", "")
                            
                            message = ChatMessage(
                                role.name, 
                                f"[图片]: {prompt}", 
                                time.time(),
                                is_image=True,
                                image_url=image_url,
                                image_data=image_data,
                                image_prompt=prompt
                            )
                            self.messages.append(message)
                            
                            message_data = message.to_dict()
                            message_data["char_count"] = len(prompt)
                            message_data["message_index"] = message_index
                            await self.notify("message", message_data)
                            last_active_time = asyncio.get_event_loop().time()
                        else:
                            error_msg = f"图片生成失败: {image_result.get('error', '未知错误')}"
                            message = ChatMessage(role.name, error_msg, time.time())
                            self.messages.append(message)
                            
                            message_data = message.to_dict()
                            message_data["char_count"] = len(error_msg)
                            message_data["message_index"] = message_index
                            await self.notify("message", message_data)
                            last_active_time = asyncio.get_event_loop().time()
                    elif role.model_type == "video":
                        # 获取上一个角色的发言作为提示词
                        last_message = ""
                        if self.messages:
                            last_message = self.messages[-1].content
                        
                        video_result = await self.generate_video_response(role, last_message, theme)
                        
                        if video_result["success"]:
                            video_url = video_result.get("video_url", "")
                            prompt = video_result.get("prompt", "")
                            
                            message = ChatMessage(
                                role.name, 
                                f"[视频]: {prompt}", 
                                time.time(),
                                is_video=True,
                                video_url=video_url,
                                video_prompt=prompt
                            )
                            self.messages.append(message)
                            
                            message_data = message.to_dict()
                            message_data["char_count"] = len(prompt)
                            message_data["message_index"] = message_index
                            await self.notify("message", message_data)
                            last_active_time = asyncio.get_event_loop().time()
                        else:
                            error_msg = f"视频生成失败: {video_result.get('error', '未知错误')}"
                            message = ChatMessage(role.name, error_msg, time.time())
                            self.messages.append(message)
                            
                            message_data = message.to_dict()
                            message_data["char_count"] = len(error_msg)
                            message_data["message_index"] = message_index
                            await self.notify("message", message_data)
                            last_active_time = asyncio.get_event_loop().time()
                    else:
                        search_info = ""
                        if round_count % 3 == 0:
                            search_info = await self.search_for_info(f"{theme} {context[:100]}")
                        
                        full_response = ""
                        async for chunk in self.generate_response_stream(role, context, theme, search_info):
                            if not self.is_chatting:
                                break
                            full_response += chunk
                            await self.notify("message_chunk", {
                                "role_name": role.name,
                                "chunk": chunk,
                                "full_content": full_response
                            })
                        
                        message = ChatMessage(role.name, full_response, time.time())
                        self.messages.append(message)
                        
                        message_data = message.to_dict()
                        message_data["char_count"] = len(full_response)
                        message_data["message_index"] = message_index
                        await self.notify("message", message_data)
                    
                    await asyncio.sleep(1)
                
                round_count += 1
                
                # 每轮结束后检查是否需要停止（保存逻辑统一放到 finally）
                if not self.is_chatting:
                    logger.info(f"聊天停止信号: {len(self.messages)}条消息")
                    break
                
                # 检测WebSocket是否已断开（超过10秒没有活跃连接）
                if len(self.websockets) == 0 and asyncio.get_event_loop().time() - last_active_time > 10:
                    logger.warning("WebSocket已断开，自动停止聊天并保存记录")
                    self.is_chatting = False
                    break
        except asyncio.CancelledError:
            logger.info("聊天任务被取消")
        except Exception as e:
            logger.error(f"聊天循环异常: {e}")
        finally:
            try:
                self.is_chatting = False
                # 通知前端聊天结束
                await self.notify("chat_ended", {"message": "聊天已结束", "message_count": len(self.messages)})
                # 聊天结束时自动保存聊天记录（唯一保存入口）
                logger.info(f"聊天结束，保存记录: {len(self.messages)}条消息, 主题: {self.current_theme}")
                session_id = self.save_current_chat()
                if session_id:
                    logger.info(f"保存成功: session_id={session_id}")
                else:
                    logger.warning("保存失败或跳过")
            except Exception as e:
                logger.error(f"聊天结束时处理异常: {e}", exc_info=True)
            finally:
                # 在外部finally中发送stopped通知
                try:
                    await self.notify("stopped", {})
                except:
                    pass
    
    async def start_chat(self, theme: Optional[str] = None):
        """Start the chat session"""
        if self.is_chatting:
            return False
        
        if len(self.roles) < 2:
            return False
        
        if not theme:
            theme = await self.generate_theme()
        
        self.is_chatting = True
        self.chat_task = asyncio.create_task(self.chat_loop(theme))
        
        return True
    
    async def stop_chat(self):
        """Stop the chat session"""
        self.is_chatting = False
        if self.chat_task:
            self.chat_task.cancel()
            # 等待任务结束，最多3秒；保存由 chat_loop 的 finally 统一处理
            try:
                await asyncio.wait_for(self.chat_task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            finally:
                self.chat_task = None
    
    def get_status(self) -> Dict:
        """Get current chat status"""
        return {
            "is_chatting": self.is_chatting,
            "theme": self.current_theme,
            "role_count": len(self.roles),
            "message_count": len(self.messages)
        }


ai_chat_manager = AIChatManager()