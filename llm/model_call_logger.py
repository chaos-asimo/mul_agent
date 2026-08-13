"""模型调用日志管理器 - 高性能版"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
import json
import os
import queue
import threading
import time
import uuid


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
    """模型调用日志管理器 - 高性能版"""
    
    def __init__(self, log_dir: str = "logs", 
                 max_memory_entries: int = 1000,
                 batch_size: int = 10,
                 flush_interval: float = 2.0,
                 retention_days: int = 30):
        """
        初始化日志管理器
        
        Args:
            log_dir: 日志存储目录
            max_memory_entries: 内存中保留的最大日志条数
            batch_size: 批量写入的数量阈值
            flush_interval: 自动刷新间隔（秒）
            retention_days: 日志保留天数
        """
        self.log_dir = log_dir
        self.max_memory_entries = max_memory_entries
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.retention_days = retention_days
        
        # 内存中的日志列表（只保留最近N条）
        self.call_logs: List[ModelCallLog] = []
        
        # 日志索引：log_id -> (date_str, line_number)
        self._log_index: Dict[str, tuple] = {}
        
        # 回调函数
        self._on_log_callback: Optional[Callable] = None
        
        # 异步写入相关
        self._write_queue = queue.Queue()
        self._write_thread = threading.Thread(target=self._writer_worker, daemon=True)
        self._write_thread.start()
        
        # 索引文件路径
        self._index_file = os.path.join(log_dir, "model_calls_index.json")
        
        # 确保目录存在
        os.makedirs(log_dir, exist_ok=True)
        
        # 加载索引和最近的日志
        self._load_index()
        self._load_recent_logs()
        
        # 启动定时清理任务
        self._start_cleanup_task()
    
    def _get_log_file_path(self, date_str: str) -> str:
        """获取指定日期的日志文件路径"""
        return os.path.join(self.log_dir, f"model_calls_{date_str}.log")
    
    def _get_today_file_path(self) -> str:
        """获取今天的日志文件路径"""
        return self._get_log_file_path(datetime.now().strftime("%Y-%m-%d"))
    
    def _load_index(self):
        """加载日志索引"""
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as f:
                    self._log_index = json.load(f)
        except Exception as e:
            print(f"Failed to load index: {e}")
            self._log_index = {}
    
    def _save_index(self):
        """保存日志索引"""
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(self._log_index, f, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save index: {e}")
    
    def _load_recent_logs(self):
        """加载最近的日志到内存"""
        try:
            # 查找最近的日志文件
            log_files = sorted([f for f in os.listdir(self.log_dir) 
                               if f.startswith("model_calls_") and f.endswith(".log")],
                              reverse=True)
            
            loaded_count = 0
            for log_file in log_files:
                if loaded_count >= self.max_memory_entries:
                    break
                
                file_path = os.path.join(self.log_dir, log_file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        # 从文件末尾开始加载，直到达到内存限制
                        start_idx = max(0, len(lines) - (self.max_memory_entries - loaded_count))
                        for line in lines[start_idx:]:
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
                                    loaded_count += 1
                                except Exception as e:
                                    print(f"Failed to parse log line: {e}")
                except Exception as e:
                    print(f"Failed to load log file {log_file}: {e}")
            
            # 按时间排序
            self.call_logs.sort(key=lambda x: x.timestamp)
            
        except Exception as e:
            print(f"Failed to load recent logs: {e}")
    
    def _writer_worker(self):
        """后台写入线程"""
        buffer = []
        last_flush_time = time.time()
        
        while True:
            try:
                # 等待队列中有数据，最多等待flush_interval秒
                try:
                    log_entry = self._write_queue.get(timeout=self.flush_interval)
                    buffer.append(log_entry)
                except queue.Empty:
                    pass
                
                # 检查是否需要刷新
                current_time = time.time()
                if (len(buffer) >= self.batch_size or 
                    (buffer and current_time - last_flush_time >= self.flush_interval)):
                    self._flush_buffer(buffer)
                    buffer = []
                    last_flush_time = current_time
                    
            except Exception as e:
                print(f"Writer worker error: {e}")
                time.sleep(1)
    
    def _flush_buffer(self, buffer: List[Dict]):
        """将缓冲区数据写入文件"""
        if not buffer:
            return
        
        try:
            # 按日期分组
            by_date = {}
            for entry in buffer:
                timestamp = datetime.fromisoformat(entry["timestamp"])
                date_str = timestamp.strftime("%Y-%m-%d")
                if date_str not in by_date:
                    by_date[date_str] = []
                by_date[date_str].append(entry)
            
            # 写入各日期文件并更新索引
            for date_str, entries in by_date.items():
                file_path = self._get_log_file_path(date_str)
                # 获取文件当前行数（用于索引）
                line_number = sum(1 for _ in open(file_path, "r", encoding="utf-8")) if os.path.exists(file_path) else 0
                
                with open(file_path, "a", encoding="utf-8") as f:
                    for entry in entries:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        # 更新索引
                        self._log_index[entry["id"]] = (date_str, line_number)
                        line_number += 1
            
            # 保存索引
            self._save_index()
            
        except Exception as e:
            print(f"Failed to flush buffer: {e}")
    
    def _start_cleanup_task(self):
        """启动定时清理任务（每小时执行一次）"""
        def cleanup_worker():
            while True:
                try:
                    self._cleanup_old_logs()
                except Exception as e:
                    print(f"Cleanup error: {e}")
                time.sleep(3600)  # 每小时清理一次
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_old_logs(self):
        """清理过期的日志文件"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
            
            for filename in os.listdir(self.log_dir):
                if filename.startswith("model_calls_") and filename.endswith(".log"):
                    date_str = filename.replace("model_calls_", "").replace(".log", "")
                    if date_str < cutoff_str:
                        file_path = os.path.join(self.log_dir, filename)
                        try:
                            os.remove(file_path)
                            print(f"Cleaned up old log: {filename}")
                        except Exception as e:
                            print(f"Failed to remove {filename}: {e}")
            
            # 清理索引中引用已删除文件的条目
            to_remove = []
            for log_id, (date_str, _) in self._log_index.items():
                file_path = self._get_log_file_path(date_str)
                if not os.path.exists(file_path):
                    to_remove.append(log_id)
            
            for log_id in to_remove:
                del self._log_index[log_id]
            
            if to_remove:
                self._save_index()
                
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    def set_log_callback(self, callback: Callable):
        """设置日志回调函数，用于实时通知前端"""
        self._on_log_callback = callback
    
    def log_call(self, model_name: str, messages: List[Dict[str, str]], 
                 response: str, total_tokens: int, prompt_tokens: int, 
                 completion_tokens: int, duration: float, error: Optional[str] = None):
        """记录模型调用（高性能版）"""
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
        
        # 添加到内存（保持最新）
        self.call_logs.append(log_entry)
        
        # 内存超过限制时，移除最旧的记录
        while len(self.call_logs) > self.max_memory_entries:
            self.call_logs.pop(0)
        
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
        
        # 放入异步写入队列
        self._write_queue.put(log_entry.to_dict())
    
    def get_logs(self, limit: int = 20) -> List[Dict]:
        """获取最近的日志列表"""
        recent = self.call_logs[-limit:]
        return [log.to_dict() for log in reversed(recent)]
    
    def get_log_by_id(self, log_id: str) -> Optional[Dict]:
        """根据ID获取日志（支持从历史文件中查找）"""
        # 先在内存中查找
        for log in self.call_logs:
            if log.id == log_id:
                return log.to_dict()
        
        # 如果不在内存中，从索引查找文件位置
        if log_id in self._log_index:
            date_str, line_number = self._log_index[log_id]
            file_path = self._get_log_file_path(date_str)
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i == line_number:
                            data = json.loads(line.strip())
                            return data
            except Exception as e:
                print(f"Failed to read log by id {log_id}: {e}")
        
        return None
    
    def get_all_logs(self) -> List[Dict]:
        """获取所有日志（从文件中读取，用于统计）"""
        all_logs = []
        
        try:
            log_files = sorted([f for f in os.listdir(self.log_dir) 
                               if f.startswith("model_calls_") and f.endswith(".log")])
            
            for log_file in log_files:
                file_path = os.path.join(self.log_dir, log_file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    data = json.loads(line)
                                    all_logs.append(data)
                                except Exception as e:
                                    print(f"Failed to parse log line: {e}")
                except Exception as e:
                    print(f"Failed to read log file {log_file}: {e}")
        
        except Exception as e:
            print(f"Failed to get all logs: {e}")
        
        return all_logs
    
    def clear_logs(self):
        """清空所有日志"""
        self.call_logs = []
        self._log_index = {}
        
        # 删除所有日志文件
        for filename in os.listdir(self.log_dir):
            if filename.startswith("model_calls_") and filename.endswith(".log"):
                try:
                    os.remove(os.path.join(self.log_dir, filename))
                except Exception as e:
                    print(f"Failed to remove {filename}: {e}")
        
        # 删除索引文件
        if os.path.exists(self._index_file):
            os.remove(self._index_file)
    
    def flush(self):
        """强制刷新所有缓冲数据"""
        # 等待队列中的数据处理完毕
        while not self._write_queue.empty():
            time.sleep(0.1)
        # 等待缓冲区刷新
        time.sleep(0.5)


# 全局日志实例
model_call_logger = ModelCallLogger()
