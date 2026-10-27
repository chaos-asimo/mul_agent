"""OpenAI API adapter"""
import os
import time
from typing import List, Dict, Optional
from openai import OpenAI
from .adapter_base import LLMAdapter, LLMResponse
from .model_call_logger import model_call_logger


class _ToolStreamIter:
    """懒加载流式迭代器：__iter__ 时实时从 OpenAI stream 读取并逐 chunk yield，
    实现真正的流式输出。消费完后在对象上设置 .tool_calls 属性，
    供 ReActLoop 提取工具调用结果。"""

    def __init__(self, adapter, messages, tools, kwargs):
        self._adapter = adapter
        self._messages = messages
        self._tools = tools
        self._kwargs = kwargs
        self.tool_calls = None  # 流消费完后设置
        self._full_content = ""
        self._tool_calls_buf = []

    def __iter__(self):
        start = time.time()
        try:
            stream = self._adapter.client.chat.completions.create(
                model=self._adapter.model_name,
                messages=self._messages,
                tools=self._tools,
                tool_choice="auto",
                temperature=self._kwargs.get("temperature", 0.7),
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    self._full_content += delta.content
                    yield {"type": "content", "content": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        while len(self._tool_calls_buf) <= idx:
                            self._tool_calls_buf.append({"id": "", "name": "", "arguments": ""})
                        if tc.id:
                            self._tool_calls_buf[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            self._tool_calls_buf[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            self._tool_calls_buf[idx]["arguments"] += tc.function.arguments
            # 流正常结束
            self.tool_calls = [tc for tc in self._tool_calls_buf if tc.get("name")]
            duration = time.time() - start
            pt = len(str(self._messages)) // 3
            ct = len(self._full_content) // 3
            model_call_logger.log_call(
                model_name=self._adapter.model_name,
                messages=self._messages,
                response=self._full_content,
                total_tokens=pt + ct, prompt_tokens=pt, completion_tokens=ct,
                duration=duration,
            )
            yield {"type": "stats", "stats": {
                "prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct,
            }}
        except Exception as e:
            self.tool_calls = []
            duration = time.time() - start
            model_call_logger.log_call(
                model_name=self._adapter.model_name,
                messages=self._messages, response="",
                total_tokens=0, prompt_tokens=0, completion_tokens=0,
                duration=duration, error=str(e),
            )
            yield {"type": "content", "content": f"⚠️ 模型调用失败：{str(e)[:200]}"}


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

    def chat_stream(self, messages: List[Dict[str, str]], **kwargs):
        """Send streaming chat request to OpenAI API, yields chunks"""
        import time
        import json
        start_time = time.time()
        first_token_time = None
        full_response = ""
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0

        try:
            create_kwargs = dict(
                model=self.model_name,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                top_p=kwargs.get("top_p", 1.0),
                stream=True
            )
            # 默认不限制 max_tokens；调用方显式传入时生效（如 PPT 大纲生成需要更长输出）
            if kwargs.get("max_tokens"):
                create_kwargs["max_tokens"] = kwargs["max_tokens"]
            stream = self.client.chat.completions.create(**create_kwargs)
            
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content is not None:
                    if first_token_time is None:
                        first_token_time = time.time()
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield content
            
            # 流结束后，获取完整的token使用统计
            duration = time.time() - start_time
            
            # 使用字符数估算 token（中文约 2 字符/token，英文约 4 字符/token）
            # 这是一个粗略估算，对于准确的统计需要使用 tiktoken
            if messages:
                messages_str = str(messages)
                # 简单估算：中文按2字符/token，英文按4字符/token
                prompt_tokens = len(messages_str) // 3
            
            if full_response:
                completion_tokens = len(full_response) // 3
            
            total_tokens = prompt_tokens + completion_tokens
            
            # 记录调用日志
            ttft = (first_token_time - start_time) if first_token_time else 0.0
            model_call_logger.log_call(
                model_name=self.model_name,
                messages=messages,
                response=full_response,
                total_tokens=total_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration=duration,
                ttft=ttft
            )
            
            # 发送 token 统计信息（作为特殊的 chunk）
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

    def supports_tools(self) -> bool:
        return True

    def chat_stream_with_tools(self, messages, tools, **kwargs):
        """OpenAI function calling：真正的流式输出 + 工具调用收集。
        返回 _ToolStreamIter 对象，其 __iter__ 是懒加载生成器——
        调用方 for chunk in resp 时实时从 OpenAI stream 读取并逐 chunk yield，
        流结束后对象上设置 .tool_calls 属性供 ReActLoop 提取。"""
        return _ToolStreamIter(self, messages, tools, kwargs)

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken"""
        try:
            encoding = tiktoken.encoding_for_model(self.model_name)
            return len(encoding.encode(text))
        except Exception:
            # Fallback: rough estimate
            return len(text) // 4

    def embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API"""
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=texts
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            print(f"Embedding API error: {e}")
            raise
