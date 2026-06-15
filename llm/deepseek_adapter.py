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

            content = response.choices[0].message.content or ""

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

    def count_tokens(self, text: str) -> int:
        """Count tokens - use GPT tokenizer as approximation"""
        try:
            from tiktoken import encoding_for_model
            encoding = encoding_for_model("gpt-3.5-turbo")
            return len(encoding.encode(text))
        except Exception:
            return len(text) // 4
