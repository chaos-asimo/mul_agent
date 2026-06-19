"""Base class for LLM adapters"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import tiktoken


@dataclass
class LLMResponse:
    """LLM response container"""
    content: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    raw_response: Optional[Dict] = None


class LLMAdapter(ABC):
    """Abstract base class for LLM adapters"""

    def __init__(self, api_key: str, model_name: str, api_url: str = ""):
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = api_url
        self._tokenizer = None

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat request to LLM"""
        pass

    @abstractmethod
    def chat_stream(self, messages: List[Dict[str, str]], **kwargs):
        """Send streaming chat request to LLM, yields chunks"""
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        pass

    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count tokens in messages"""
        total = 0
        for msg in messages:
            total += 3  # overhead per message
            total += len(msg.get("content", ""))
        return total

    def summarize_context(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> List[Dict[str, str]]:
        """Summarize context to fit within token limit"""
        if not messages:
            return []

        # Simple summarization: keep system message and last few user messages
        system_msg = None
        other_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg
            else:
                other_messages.append(msg)

        # Keep last 2 messages if too many
        if len(other_messages) > 2:
            other_messages = other_messages[-2:]

        result = []
        if system_msg:
            result.append(system_msg)

        # Add summary instruction
        summary_instruction = {
            "role": "system",
            "content": "[注意：之前的对话已被摘要精简以节省上下文空间]"
        }
        result.append(summary_instruction)
        result.extend(other_messages)

        return result

    def create_prompt(self, system_prompt: str, user_input: str, context: List[Dict[str, str]] = None) -> List[Dict[str, str]]:
        """Create prompt with context"""
        messages = []

        if context:
            for msg in context:
                if msg.get("role") != "system":
                    messages.append(msg)

        messages.insert(0, {"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_input})
        return messages
