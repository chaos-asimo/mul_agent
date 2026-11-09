# -*- coding: utf-8 -*-
"""HITL 人机协作确认管理器：medium/high 风险工具执行前需用户确认。"""
import threading
import uuid
from typing import Dict


class ConfirmManager:
    """进程内确认请求队列，供 SSE 推送 + HTTP 回调解耦。"""

    def __init__(self):
        self._pending: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def request(self) -> str:
        rid = uuid.uuid4().hex
        with self._lock:
            self._pending[rid] = {"event": threading.Event(), "approved": False}
        return rid

    def wait(self, request_id: str, timeout: float = 300.0) -> bool:
        item = self._pending.get(request_id)
        if not item:
            return False
        item["event"].wait(timeout)
        return item["approved"]

    def resolve(self, request_id: str, approved: bool) -> bool:
        item = self._pending.pop(request_id, None)
        if not item:
            return False
        item["approved"] = approved
        item["event"].set()
        return True

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)


confirm_manager = ConfirmManager()
