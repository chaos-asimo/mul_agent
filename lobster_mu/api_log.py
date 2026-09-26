# -*- coding: utf-8 -*-
"""多用户龙虾Claw - 接口访问日志（记录 /api/lobster-mu 请求，仅管理员可查）

性能优化：
- 日志先写入线程安全内存队列（非阻塞），请求路径几乎零开销
- 后台守护线程定时/定量批量 INSERT（单事务），大幅减少 SQLite WAL 写锁获取次数与持有时间
  （旧实现：每个请求一次 connect + INSERT + commit + close，并发时写锁排队导致 2~30s 延迟）
"""
import threading
from collections import deque
from datetime import datetime

from lobster_mu import db

_QUEUE: deque = deque()
_QUEUE_LOCK = threading.Lock()
_QUEUE_COND = threading.Condition(_QUEUE_LOCK)
_STOP = threading.Event()
_STARTED = threading.Event()

# 批量落盘参数
FLUSH_INTERVAL = 1.0    # 最多等待 1 秒
QUEUE_MAXLEN = 20000    # 队列上限，超出丢弃最旧（日志可丢弃，不能拖垮请求）

_LOG_SQL = (
    "INSERT INTO mu_api_access_logs "
    "(method, path, status, duration_ms, ip, username, user_id, auth_type, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def log_api_access(
    method: str,
    path: str,
    status: int,
    duration_ms: int,
    ip: str = "",
    username: str = "",
    user_id: int = 0,
    auth_type: str = "",
):
    """投递一条接口访问日志到内存队列（非阻塞，立即返回）。

    实际写库由后台守护线程批量完成，调用方无需再包装线程池。
    任何异常静默吞掉，绝不影响请求。
    """
    try:
        row = (
            method,
            path,
            status,
            duration_ms,
            ip,
            username,
            user_id,
            auth_type,
            datetime.now().isoformat(),
        )
        with _QUEUE_LOCK:
            _QUEUE.append(row)
            if len(_QUEUE) > QUEUE_MAXLEN:
                _QUEUE.popleft()
        _ensure_started()
        _QUEUE_COND.notify()
    except Exception:
        pass


def _ensure_started():
    """懒启动后台刷写线程（首个日志到来时创建）"""
    if not _STARTED.is_set():
        _STARTED.set()
        t = threading.Thread(target=_flush_worker, name="mu-api-log-flusher", daemon=True)
        t.start()


def _flush_worker():
    """后台守护线程：定时/定量批量落盘"""
    while not _STOP.is_set():
        with _QUEUE_COND:
            # 等待：有数据可刷 或 达到刷写间隔 或 收到停止信号
            _QUEUE_COND.wait(timeout=FLUSH_INTERVAL)
            if _STOP.is_set() and not _QUEUE:
                break
            batch = list(_QUEUE)
            _QUEUE.clear()
        if not batch:
            continue
        _flush_batch(batch)
    # 退出前把队列里残留的日志也刷掉
    with _QUEUE_LOCK:
        remaining = list(_QUEUE)
        _QUEUE.clear()
    if remaining:
        _flush_batch(remaining)


_DB_READY = False
_DB_READY_LOCK = threading.Lock()


def _ensure_db_once():
    """进程内只执行一次建库（含全部 DDL 与列迁移）。

    旧实现在每次批量落盘前都调用 db.init_db()，导致后台线程每秒重跑
    39 条 DDL + 4 张表迁移检查，持续占用 WAL 写锁，与前台请求竞争，
    是「用户管理列表查询慢、刷新后变快」的根因。
    """
    global _DB_READY
    if _DB_READY:
        return
    with _DB_READY_LOCK:
        if _DB_READY:
            return
        try:
            db.init_db()
            _DB_READY = True
        except Exception:
            # 建库失败时不置位，下批重试
            pass


def _flush_batch(rows):
    """单事务批量 INSERT；失败时回滚并逐条重试，避免整批丢失"""
    _ensure_db_once()
    conn = None
    try:
        conn = db.get_conn()
        try:
            conn.executemany(_LOG_SQL, rows)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            # 兜底：逐条插入，尽量抢救
            for r in rows:
                try:
                    conn.execute(_LOG_SQL, r)
                    conn.commit()
                except Exception:
                    continue
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def stop():
    """停止后台刷写线程（测试 / 优雅关闭用）"""
    _STOP.set()
    with _QUEUE_COND:
        _QUEUE_COND.notify()
