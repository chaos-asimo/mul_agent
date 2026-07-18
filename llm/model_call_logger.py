"""模型调用日志管理器"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Callable
import json
import os


@dataclass
class ModelCallLog:
    """模型调用日志条目"""
    id: str
    timestamp: datetime
    model_name: str
    messages: List[Dict[str, str]]
    response: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    duration: float  # 调用耗时（秒）
    tokens_per_second: float = 0.0  # 每秒token输出量
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "model_name": self.model_name,
            "messages": self.messages,
            "response": self.response,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "duration": self.duration,
            "tokens_per_second": self.tokens_per_second,
            "error": self.error
        }
    
    def get_summary(self) -> str:
        """获取日志摘要"""
        if self.error:
            return f"[{self.model_name}] 错误: {self.error}"
        
        tps = self.tokens_per_second
        return (f"[{self.model_name}] "
                f"输入: {self.prompt_tokens} tokens | "
                f"输出: {self.completion_tokens} tokens | "
                f"耗时: {self.duration:.2f}s | "
                f"速度: {tps:.1f} tokens/s")


class ModelCallLogger:
    """模型调用日志管理器"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, "model_calls.log")
        self.call_logs: List[ModelCallLog] = []
        self._on_log_callback: Optional[Callable] = None  # 回调函数，用于实时通知
        os.makedirs(log_dir, exist_ok=True)
        self._load_logs()
    
    def set_log_callback(self, callback: Callable):
        """设置日志回调函数，用于实时通知前端"""
        self._on_log_callback = callback
    
    def _load_logs(self):
        """加载已保存的日志"""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                log = ModelCallLog(
                                    id=data["id"],
                                    timestamp=datetime.fromisoformat(data["timestamp"]),
                                    model_name=data["model_name"],
                                    messages=data["messages"],
                                    response=data["response"],
                                    total_tokens=data["total_tokens"],
                                    prompt_tokens=data["prompt_tokens"],
                                    completion_tokens=data["completion_tokens"],
                                    duration=data["duration"],
                                    tokens_per_second=data.get("tokens_per_second", 0.0),
                                    error=data.get("error")
                                )
                                self.call_logs.append(log)
                            except Exception as e:
                                print(f"Failed to parse log line: {e}")
        except Exception as e:
            print(f"Failed to load logs: {e}")
    
    def log_call(self, model_name: str, messages: List[Dict[str, str]], 
                 response: str, total_tokens: int, prompt_tokens: int, 
                 completion_tokens: int, duration: float, error: Optional[str] = None):
        """记录模型调用"""
        import uuid
        
        # 计算每秒token输出量
        tokens_per_second = completion_tokens / duration if duration > 0 else 0.0
        
        log_entry = ModelCallLog(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            model_name=model_name,
            messages=messages,
            response=response,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration=duration,
            tokens_per_second=tokens_per_second,
            error=error
        )
        
        self.call_logs.append(log_entry)
        
        # 打印详细日志到控制台
        summary = log_entry.get_summary()
        print(f"[INFO] {summary}")
        if error:
            print(f"   [ERROR] 错误: {error}")
        
        # 调用回调函数，通知前端
        if self._on_log_callback:
            try:
                self._on_log_callback(log_entry)
            except Exception as e:
                print(f"Callback error: {e}")
        
        # 保存到文件
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")
    
    def get_logs(self, limit: int = 20) -> List[Dict]:
        """获取日志列表"""
        recent = self.call_logs[-limit:]
        return [log.to_dict() for log in reversed(recent)]
    
    def get_log_by_id(self, log_id: str) -> Optional[Dict]:
        """根据ID获取日志"""
        for log in self.call_logs:
            if log.id == log_id:
                return log.to_dict()
        return None
    
    def clear_logs(self):
        """清空日志"""
        self.call_logs = []
        if os.path.exists(self.log_file):
            os.remove(self.log_file)


# 全局日志实例
model_call_logger = ModelCallLogger()