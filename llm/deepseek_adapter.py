"""DeepSeek API adapter"""
from typing import List, Dict, Optional
from openai import OpenAI
from .adapter_base import LLMAdapter, LLMResponse


class DeepSeekAdapter(LLMAdapter):
    """DeepSeek API adapter"""

    def __init__(self, api_key: str, model_name: str, api_url: str = ""):
        super().__init__(api_key, model_name, api_url)
        url = api_url or "https://api.deepseek.com/v1"
        self.client = OpenAI(api_key=api_key, base_url=url)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat request to DeepSeek API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
            )

            content = response.choices[0].message.content if response.choices and len(response.choices) > 0 else ""

            return LLMResponse(
                content=content,
                total_tokens=response.usage.total_tokens if response.usage else 0,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
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
        """Send streaming chat request to DeepSeek API, yields chunks"""
        import time
        from .model_call_logger import model_call_logger
        start_time = time.time()
        full_response = ""
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        
        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield content
            
            # 流结束后，计算 token 统计
            duration = time.time() - start_time
            
            # 使用字符数估算 token
            if messages:
                messages_str = str(messages)
                prompt_tokens = len(messages_str) // 3
            
            if full_response:
                completion_tokens = len(full_response) // 3
            
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
        """Count tokens - use GPT tokenizer as approximation"""
        try:
            from tiktoken import encoding_for_model
            encoding = encoding_for_model("gpt-3.5-turbo")
            return len(encoding.encode(text))
        except Exception:
            return len(text) // 4
