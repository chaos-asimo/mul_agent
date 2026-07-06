"""Agent worker for executing agent tasks"""
import time
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from llm.adapter_base import LLMAdapter, LLMResponse
from llm.image_adapter import ImageAdapter, ImageResponse
from llm.video_adapter import VideoAdapter, VideoResponse, AgnesVideoAdapter, OpenAIVideoAdapter
from llm import OpenAIAdapter, ClaudeAdapter, DeepSeekAdapter
from llm.dalle_adapter import DALLEAdapter
from llm.sd_adapter import StableDiffusionAdapter
from agents.agent_config import AgentConfig
from models.model_config import ModelConfig


@dataclass
class AgentResult:
    """Result from agent execution"""
    agent_id: str
    agent_name: str
    model_name: str = ""  # 使用的模型名称
    input_content: str = ""  # 输入内容
    output: str = ""
    optimization_summary: str = ""  # 本次优化摘要
    prompt_tokens: int = 0  # 输入token数
    completion_tokens: int = 0  # 输出token数
    tokens_used: int = 0  # 总token数
    time_spent: float = 0.0  # in seconds
    self_evaluation: str = ""
    success: bool = True
    error_message: str = ""


class AgentWorker:
    """Worker class for running agent tasks"""

    def __init__(self, agent_config: AgentConfig, model_config: ModelConfig, llm_adapter: LLMAdapter):
        self.agent_config = agent_config
        self.model_config = model_config
        self.llm_adapter = llm_adapter
        # 不保留历史上下文，每次运行都是新的
        self.context: List[Dict[str, str]] = []
        self.total_tokens_used = 0
        self.total_time_spent = 0.0

    def reset_context(self):
        """Reset agent context - 每次运行前清空"""
        self.context = []

    def add_to_context(self, role: str, content: str):
        """Add message to context - 不再使用，保持空上下文"""
        pass  # 不添加任何内容到上下文

    def _check_and_summarize_context(self) -> bool:
        """Check if context needs summarization - 不再需要，上下文始终为空"""
        return False  # 不进行摘要

    def run(self, user_input: str) -> AgentResult:
        """Run the agent with user input - 只使用当前输入，不保留历史上下文"""
        start_time = time.time()
        input_content = user_input  # 保存输入内容

        try:
            # 不保留历史上下文，每次运行都是独立的
            # Build prompt - 只使用系统提示和当前输入
            messages = self.llm_adapter.create_prompt(
                system_prompt=self.agent_config.role_description,
                user_input=user_input,
                context=[]  # 空上下文
            )

            # Call LLM
            response = self.llm_adapter.chat(messages)

            time_spent = time.time() - start_time

            if response.total_tokens == 0 and response.content.startswith("Error:"):
                return AgentResult(
                    agent_id=self.agent_config.id,
                    agent_name=self.agent_config.name,
                    model_name=self.model_config.name,
                    input_content=input_content,
                    output="",
                    tokens_used=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    time_spent=time_spent,
                    self_evaluation="",
                    success=False,
                    error_message=response.content
                )

            # 不保留历史上下文，不添加到context

            # Generate self-evaluation and optimization summary
            evaluation = self._generate_self_evaluation(input_content, response.content)
            opt_summary = self._generate_optimization_summary(input_content, response.content)

            # Update stats
            self.total_tokens_used += response.total_tokens
            self.total_time_spent += time_spent

            return AgentResult(
                agent_id=self.agent_config.id,
                agent_name=self.agent_config.name,
                model_name=self.model_config.name,
                input_content=input_content,
                output=response.content,
                optimization_summary=opt_summary,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                tokens_used=response.total_tokens,
                time_spent=time_spent,
                self_evaluation=evaluation,
                success=True
            )

        except Exception as e:
            time_spent = time.time() - start_time
            return AgentResult(
                agent_id=self.agent_config.id,
                agent_name=self.agent_config.name,
                model_name=self.model_config.name,
                input_content=input_content,
                output="",
                tokens_used=0,
                prompt_tokens=0,
                completion_tokens=0,
                time_spent=time_spent,
                self_evaluation="",
                success=False,
                error_message=str(e)
            )

    def _generate_optimization_summary(self, input_content: str, output_content: str) -> str:
        """Generate summary of what was optimized"""
        # 简单的优化摘要：比较输入和输出的长度变化
        input_len = len(input_content)
        output_len = len(output_content)
        len_change = output_len - input_len
        
        if len_change > 0:
            change_desc = f"内容扩展了 {len_change} 字符"
        elif len_change < 0:
            change_desc = f"内容精简了 {abs(len_change)} 字符"
        else:
            change_desc = "内容长度保持不变"
        
        return f"{change_desc}。由 {self.agent_config.name} Agent 使用 {self.model_config.name} 模型处理。"

    def run_stream(self, user_input: str):
        """Run the agent with user input in streaming mode - yields chunks"""
        import json
        input_content = user_input
        log_id = None  # 保存日志ID，用于后续获取统计信息
        stats = None  # 保存 token 统计

        try:
            messages = self.llm_adapter.create_prompt(
                system_prompt=self.agent_config.role_description,
                user_input=user_input,
                context=[]
            )

            full_output = ""
            for chunk in self.llm_adapter.chat_stream(messages):
                if chunk.startswith("Error:"):
                    yield {"type": "error", "content": chunk}
                    return
                
                # 检查是否是特殊的统计 chunk
                if chunk.startswith("{\"__stats__\""):
                    try:
                        stats_data = json.loads(chunk)
                        stats = {
                            "prompt_tokens": stats_data.get("prompt_tokens", 0),
                            "completion_tokens": stats_data.get("completion_tokens", 0),
                            "total_tokens": stats_data.get("total_tokens", 0),
                            "duration": stats_data.get("duration", 0),
                            "tokens_per_second": stats_data.get("completion_tokens", 0) / stats_data.get("duration", 1) if stats_data.get("duration", 0) > 0 else 0
                        }
                    except:
                        pass
                    continue
                
                full_output += chunk
                yield {"type": "chunk", "content": chunk, "agent_name": self.agent_config.name}
            
            # 获取最新的模型调用日志统计
            from llm.model_call_logger import model_call_logger
            logs = model_call_logger.get_logs(1)
            if logs and not stats:
                log_id = logs[0].get("id")
                stats = {
                    "prompt_tokens": logs[0].get("prompt_tokens", 0),
                    "completion_tokens": logs[0].get("completion_tokens", 0),
                    "total_tokens": logs[0].get("total_tokens", 0),
                    "duration": logs[0].get("duration", 0),
                    "tokens_per_second": logs[0].get("tokens_per_second", 0)
                }
            
            if stats:
                yield {"type": "complete", "content": full_output, "agent_name": self.agent_config.name, "stats": stats}
            else:
                yield {"type": "complete", "content": full_output, "agent_name": self.agent_config.name}

        except Exception as e:
            yield {"type": "error", "content": str(e)}

    def _generate_self_evaluation(self, input_content: str, output_content: str) -> str:
        """Generate self-evaluation for the output"""
        eval_prompt = [
            {"role": "system", "content": """你是一位质量评估专家。请对以下AI输出的内容进行简短评价。
评价维度：
1. 内容质量（1-10分）
2. 与前文的连贯性（1-10分）
3. 是否遵循指令（1-10分）

请用以下格式输出：
质量评分: X/10
连贯评分: X/10
遵循评分: X/10
总体评价: 简要说明"""},
            {"role": "user", "content": f"输入内容摘要:\n{input_content[:500]}...\n\n输出内容:\n{output_content[:1000]}"}  # 评估前1000字符
        ]

        try:
            response = self.llm_adapter.chat(eval_prompt, max_tokens=500)
            return response.content
        except Exception:
            return "评价生成失败"


def create_llm_adapter(model_config: ModelConfig) -> Optional[LLMAdapter]:
    """Factory function to create LLM adapter based on model config"""
    if model_config.api_type == "openai":
        return OpenAIAdapter(
            api_key=model_config.api_key,
            model_name=model_config.model_name,
            api_url=model_config.api_url
        )
    elif model_config.api_type == "claude":
        return ClaudeAdapter(
            api_key=model_config.api_key,
            model_name=model_config.model_name,
            api_url=model_config.api_url
        )
    elif model_config.api_type == "deepseek":
        return DeepSeekAdapter(
            api_key=model_config.api_key,
            model_name=model_config.model_name,
            api_url=model_config.api_url
        )
    return None


def create_image_adapter(model_config: ModelConfig) -> Optional[ImageAdapter]:
    """Factory function to create image generation adapter based on model config"""
    if model_config.api_type == "dall-e" or model_config.api_type == "openai":
        return DALLEAdapter(
            api_key=model_config.api_key,
            api_url=model_config.api_url,
            model_name=model_config.model_name
        )
    elif model_config.api_type == "stable-diffusion":
        return StableDiffusionAdapter(
            api_key=model_config.api_key,
            api_url=model_config.api_url,
            model_name=model_config.model_name
        )
    return None


def create_video_adapter(model_config: ModelConfig) -> Optional[VideoAdapter]:
    """Factory function to create video generation adapter based on model config"""
    if model_config.api_type in ("openai", "custom"):
        # 如果是OpenAI兼容接口使用OpenAIVideoAdapter，否则使用AgnesVideoAdapter
        if model_config.model_name and model_config.model_name.startswith("sora"):
            return OpenAIVideoAdapter(
                api_key=model_config.api_key,
                api_url=model_config.api_url,
                model_name=model_config.model_name
            )
        return AgnesVideoAdapter(
            api_key=model_config.api_key,
            api_url=model_config.api_url,
            model_name=model_config.model_name
        )
    return None


def create_adapter(model_config: ModelConfig):
    """Factory function to create adapter based on model config (generic)"""
    if model_config.model_type == "image":
        return create_image_adapter(model_config)
    elif model_config.model_type == "video":
        return create_video_adapter(model_config)
    else:
        return create_llm_adapter(model_config)
