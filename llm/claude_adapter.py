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

            content = response.content[0].text if response.content else ""

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

    def count_tokens(self, text: str) -> int:
        """Count tokens - Claude uses different method"""
        # Rough estimate: Claude tokenizes roughly at 3-4 chars per token
        return len(text) // 4
