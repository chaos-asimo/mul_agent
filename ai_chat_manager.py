"""AI Chat Manager for multi-agent conversation"""
import asyncio
import random
from typing import List, Dict, Optional
from agents import AgentManager
from models import ModelManager
from search import SearchManager
from engine.agent_worker import create_llm_adapter, create_image_adapter


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
    
    def __init__(self, role_name: str, content: str, timestamp: float):
        self.role_name = role_name
        self.content = content
        self.timestamp = timestamp
    
    def to_dict(self) -> Dict:
        return {
            "role_name": self.role_name,
            "content": self.content,
            "timestamp": self.timestamp
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
                await ws.send_json({"event": event_type, "data": data})
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
        available_models = [m for m in self.model_manager.get_all() if m.api_key and m.enabled]
        if not available_models:
            return None
        
        agent = self.agent_manager.get(agent_id)
        if agent and agent.model_id:
            model = self.model_manager.get(agent.model_id)
            if model and model.api_key and model.enabled:
                return model.to_dict()
        
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
        
        try:
            messages = role.adapter.create_prompt(system_prompt, user_prompt, [])
            
            full_content = ""
            import asyncio as gen_asyncio
            from queue import Queue
            
            chunk_queue = Queue()
            
            def stream_worker():
                try:
                    for chunk in role.adapter.chat_stream(messages):
                        if isinstance(chunk, str) and chunk.startswith('{"__stats__"'):
                            continue
                        chunk_queue.put(chunk)
                except Exception as e:
                    chunk_queue.put(f"Error: {str(e)}")
                chunk_queue.put(None)
            
            gen_asyncio.get_event_loop().run_in_executor(None, stream_worker)
            
            while True:
                try:
                    chunk = await gen_asyncio.get_event_loop().run_in_executor(None, chunk_queue.get, True, 0.1)
                    if chunk is None:
                        break
                    if chunk.startswith("Error:"):
                        yield chunk
                        return
                    full_content += chunk
                    # 不在流式输出过程中截断，让大模型自然完成
                    yield chunk
                except:
                    continue
            
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
        
        while self.is_chatting and round_count < max_rounds:
            for role in self.roles:
                if not self.is_chatting:
                    break
                
                message_index += 1
                
                await self.notify("typing", {"role_name": role.name})
                
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
                    
                    import time
                    if image_result["success"]:
                        image_url = image_result.get("image_url", "")
                        image_data = image_result.get("image_data", "")
                        prompt = image_result.get("prompt", "")
                        
                        message = ChatMessage(role.name, f"[图片]: {prompt}", time.time())
                        self.messages.append(message)
                        
                        message_data = message.to_dict()
                        message_data["char_count"] = len(prompt)
                        message_data["message_index"] = message_index
                        message_data["is_image"] = True
                        message_data["image_url"] = image_url
                        message_data["image_data"] = image_data
                        message_data["image_prompt"] = prompt
                        await self.notify("message", message_data)
                    else:
                        error_msg = f"图片生成失败: {image_result.get('error', '未知错误')}"
                        message = ChatMessage(role.name, error_msg, time.time())
                        self.messages.append(message)
                        
                        message_data = message.to_dict()
                        message_data["char_count"] = len(error_msg)
                        message_data["message_index"] = message_index
                        await self.notify("message", message_data)
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
                    
                    import time
                    message = ChatMessage(role.name, full_response, time.time())
                    self.messages.append(message)
                    
                    message_data = message.to_dict()
                    message_data["char_count"] = len(full_response)
                    message_data["message_index"] = message_index
                    await self.notify("message", message_data)
                
                await asyncio.sleep(1)
            
            round_count += 1
        
        self.is_chatting = False
        await self.notify("stopped", {})
    
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
            try:
                self.chat_task.cancel()
            except:
                pass
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