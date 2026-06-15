"""Log entry data class"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class LogEntry:
    """Log entry for agent output"""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    agent_id: str = ""
    agent_name: str = ""
    model_name: str = ""  # 使用的模型名称
    iteration: int = 0
    step: int = 0
    input_content: str = ""  # 输入内容（本次优化前的内容）
    output: str = ""  # 输出内容（本次优化后的内容）
    optimization_summary: str = ""  # 本次优化的内容摘要
    prompt_tokens: int = 0  # 输入token数
    completion_tokens: int = 0  # 输出token数
    tokens_used: int = 0  # 总token数
    time_spent: float = 0.0
    self_evaluation: str = ""
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_formatted_string(self) -> str:
        """Convert to formatted string for file output"""
        status = "成功" if self.success else "失败"
        eval_section = f"\n自我评价:\n{self.self_evaluation}" if self.self_evaluation else ""
        opt_section = f"\n本次优化内容:\n{self.optimization_summary}" if self.optimization_summary else ""
        model_section = f"\n使用模型: {self.model_name}" if self.model_name else ""

        return f"""{'='*60}
时间戳: {self.timestamp}
Agent: {self.agent_name} (ID: {self.agent_id}){model_section}
迭代: 第{self.iteration}轮 第{self.step}步
状态: {status}
耗时: {self.time_spent:.2f}秒
Token详情: 输入 {self.prompt_tokens} / 输出 {self.completion_tokens} / 总计 {self.tokens_used}
{'错误信息: ' + self.error_message if not self.success else ''}{opt_section}{eval_section}
{'='*60}
输入内容:
{self.input_content[:500] if self.input_content else '[无]'}...
{'='*60}
输出内容:
{self.output}
{'='*60}
"""

    def to_brief_string(self) -> str:
        """Convert to brief string for display"""
        status = "✓" if self.success else "✗"
        model_info = f" [{self.model_name}]" if self.model_name else ""
        return f"[{self.timestamp}] {self.agent_name}{model_info}: {status} (输入{self.prompt_tokens}/输出{self.completion_tokens} tokens, {self.time_spent:.1f}s)"
