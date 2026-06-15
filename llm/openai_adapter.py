"""OpenAI API adapter"""
import os
import time
from typing import List, Dict, Optional
from openai import OpenAI
from .adapter_base import LLMAdapter, LLMResponse
from .model_call_logger import model_call_logger


class OpenAIAdapter(LLMAdapter):
    """OpenAI API adapter"""

    def __init__(self, api_key: str, model_name: str, api_url: str = ""):
        super().__init__(api_key, model_name, api_url)
        url = api_url or "https://api.openai.com/v1"
        self.client = OpenAI(api_key=api_key, base_url=url)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat request to OpenAI API"""
        start_time = time.time()
        
        try:
            # 不限制max_tokens，让模型最大化输出
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                # max_tokens不设置，让模型根据上下文自动决定输出长度
                top_p=kwargs.get("top_p", 1.0),
            )

            content = response.choices[0].message.content or ""
            duration = time.time() - start_time

            # 记录调用日志
            model_call_logger.log_call(
                model_name=self.model_name,
                messages=messages,
                response=content,
                total_tokens=response.usage.total_tokens if response.usage else 0,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                duration=duration
            )

            return LLMResponse(
                content=content,
                total_tokens=response.usage.total_tokens if response.usage else 0,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                raw_response=response.model_dump() if hasattr(response, 'model_dump') else None
            )
        except Exception as e:
            duration = time.time() - start_time
            
            # 记录错误日志
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
            
            return LLMResponse(
                content=f"Error: {str(e)}",
                total_tokens=0,
                prompt_tokens=0,
                completion_tokens=0
            )

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken"""
        try:
            encoding = tiktoken.encoding_for_model(self.model_name)
            return len(encoding.encode(text))
        except Exception:
            # Fallback: rough estimate
            return len(text) // 4
