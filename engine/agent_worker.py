"""Agent worker for executing agent tasks"""
import time
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from llm.adapter_base import LLMAdapter, LLMResponse
from llm import OpenAIAdapter, ClaudeAdapter, DeepSeekAdapter
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
