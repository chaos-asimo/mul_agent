"""Log manager for handling log files"""
import os
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from .log_entry import LogEntry


class LogManager:
    """Manages log files"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.output_dir = os.path.join(log_dir, "outputs")  # 存放每次生成的内容
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """Create logs directory if not exists"""
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def _get_log_filename(self, timestamp: str = None) -> str:
        """Generate log filename"""
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.log_dir, f"agent_log_{timestamp}.txt")

    def _get_output_filename(self, session_id: str, agent_name: str, iteration: int, step: int) -> str:
        """Generate output filename for each agent output"""
        filename = f"output_{session_id}_{agent_name}_iter{iteration}_step{step}.md"
        return os.path.join(self.output_dir, filename)

    def log_agent_result(self, result, iteration: int, step: int, session_id: str = None):
        """Log agent result to file"""
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        entry = LogEntry(
            agent_id=result.agent_id,
            agent_name=result.agent_name,
            model_name=result.model_name,
            iteration=iteration,
            step=step,
            input_content=result.input_content,
            output=result.output,
            optimization_summary=result.optimization_summary,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            tokens_used=result.tokens_used,
            time_spent=result.time_spent,
            self_evaluation=result.self_evaluation,
            success=result.success,
            error_message=result.error_message
        )

        # Log to main log file
        filename = self._get_log_filename(session_id)
        with open(filename, "a", encoding="utf-8") as f:
            f.write(entry.to_formatted_string())
            f.write("\n")

        # Save output content to separate file
        if result.output and result.success:
            output_filename = self._get_output_filename(session_id, result.agent_name, iteration, step)
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(f"# {result.agent_name} - 第{iteration}轮第{step}步输出\n\n")
                f.write(f"**使用模型**: {result.model_name}\n\n")
                f.write(f"**Token消耗**: 输入 {result.prompt_tokens} / 输出 {result.completion_tokens} / 总计 {result.tokens_used}\n\n")
                f.write(f"**耗时**: {result.time_spent:.2f}秒\n\n")
                f.write(f"**优化摘要**: {result.optimization_summary}\n\n")
                f.write("---\n\n")
                f.write("## 输出内容\n\n")
                f.write(result.output)
                f.write("\n\n---\n\n")
                f.write("## 自我评价\n\n")
                f.write(result.self_evaluation if result.self_evaluation else "无")

        return entry

    def log_session_start(self, initial_content: str, session_id: str = None):
        """Log session start"""
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = self._get_log_filename(session_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"会话开始: {timestamp}\n")
            f.write(f"{'='*60}\n")
            f.write(f"初始内容:\n{initial_content}\n")
            f.write(f"\n{'='*60}\n\n")

        return session_id

    def log_session_end(self, final_content: str, session_id: str):
        """Log session end"""
        filename = self._get_log_filename(session_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"会话结束: {timestamp}\n")
            f.write(f"{'='*60}\n")
            f.write(f"最终内容:\n{final_content}\n")
            f.write(f"{'='*60}\n")

    def get_recent_logs(self, count: int = 10) -> List[str]:
        """Get recent log files"""
        if not os.path.exists(self.log_dir):
            return []

        files = []
        for f in os.listdir(self.log_dir):
            if f.startswith("agent_log_") and f.endswith(".txt"):
                filepath = os.path.join(self.log_dir, f)
                files.append((filepath, os.path.getmtime(filepath)))

        files.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in files[:count]]

    def read_log(self, filename: str) -> Optional[str]:
        """Read a log file"""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None
