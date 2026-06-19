"""Claude API adapter"""
from typing import List, Dict, Optional
from anthropic import Anthropic
from .adapter_base import LLMAdapter, LLMResponse


class ClaudeAdapter(LLMAdapter):
    """Claude API adapter"""

    def __init__(self, api_key: str, model_name: str, api_url: str = ""):
        super().__init__(api_key, model_name, api_url)
        self.client = Anthropic(api_key=api_key)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat request to Claude API"""
        try:
            # Convert messages format for Claude
            system_prompt = ""
            claude_messages = []

            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                else:
                    claude_messages.append({
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", "")
                    })

            response = self.client.messages.create(
                model=self.model_name,
                system=system_prompt,
                messages=claude_messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
            )

            content = response.content[0].text if response.content and len(response.content) > 0 else ""

            return LLMResponse(
                content=content,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                raw_response=response.model_dump() if hasattr(response, 'model_dump') else None
            )
        except Exception as e:
            return LLMResponse(
                content=f"Error: {str(e)}",
                total_tokens=0,
                prompt_tokens=0,
                completion_tokens=0
            )

    def chat_stream(self, messages: List[Dict[str, str]], **kwargs):
        """Send streaming chat request to Claude API, yields chunks"""
        import time
        from .model_call_logger import model_call_logger
        start_time = time.time()
        full_response = ""
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        
        try:
            system_prompt = ""
            claude_messages = []

            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                else:
                    claude_messages.append({
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", "")
                    })

            stream = self.client.messages.create(
                model=self.model_name,
                system=system_prompt,
                messages=claude_messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
                stream=True
            )
            
            for chunk in stream:
                if chunk.type == "content_block_delta" and chunk.delta.text:
                    content = chunk.delta.text
                    full_response += content
                    yield content
                elif chunk.type == "content_block_start" and chunk.content_block and chunk.content_block.type == "text":
                    content = chunk.content_block.text
                    full_response += content
                    yield content
                elif chunk.type == "message_delta" and chunk.usage:
                    # 获取token使用统计
                    total_tokens = chunk.usage.output_tokens or 0
                    completion_tokens = chunk.usage.output_tokens or 0
            
            # 流结束后，计算 token 统计
            duration = time.time() - start_time
            
            # 使用字符数估算 prompt tokens
            if messages and not prompt_tokens:
                messages_str = str(messages)
                prompt_tokens = len(messages_str) // 3
            
            if not completion_tokens and full_response:
                completion_tokens = len(full_response) // 3
            
            if not total_tokens:
                total_tokens = prompt_tokens + completion_tokens
            
            # 记录调用日志
            model_call_logger.log_call(
                model_name=self.model_name,
                messages=messages,
                response=full_response,
                total_tokens=total_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration=duration
            )
            
            # 发送 token 统计信息
            yield f"{{\"__stats__\": true, \"prompt_tokens\": {prompt_tokens}, \"completion_tokens\": {completion_tokens}, \"total_tokens\": {total_tokens}, \"duration\": {duration}}}"
            
        except Exception as e:
            # 记录错误日志
            duration = time.time() - start_time
            model_call_logger.log_call(
                model_name=self.model_name,
                messages=messages,
                response="",
                total_tokens=0,
                prompt_tokens=0,
                completion_tokens=0,
                duration=duration,
                error=str(e)
            )
            yield f"Error: {str(e)}"

    def count_tokens(self, text: str) -> int:
        """Count tokens - Claude uses different method"""
        # Rough estimate: Claude tokenizes roughly at 3-4 chars per token
        return len(text) // 4
