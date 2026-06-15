"""模型调用日志管理器"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
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
            "error": self.error
        }


class ModelCallLogger:
    """模型调用日志管理器"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, "model_calls.log")
        self.call_logs: List[ModelCallLog] = []
        os.makedirs(log_dir, exist_ok=True)
        self._load_logs()
    
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
            error=error
        )
        
        self.call_logs.append(log_entry)
        
        # 保存到文件
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")
        
        # 保留最近100条日志
        if len(self.call_logs) > 100:
            self.call_logs = self.call_logs[-100:]
    
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