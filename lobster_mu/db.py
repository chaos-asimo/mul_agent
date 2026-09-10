# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - SQLite 数据库层（WAL + user_id 隔离）"""
import os
import sqlite3

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "data", "lobster_mu.db")

DDL = [
    # 用户表
    """CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT    NOT NULL UNIQUE,
        password_hash TEXT    NOT NULL,
        salt          TEXT    NOT NULL,
        role          TEXT    NOT NULL DEFAULT 'user',
        display_name  TEXT    DEFAULT '',
        disabled      INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT    NOT NULL,
        last_login_at TEXT
    )""",
    # 聊天会话
    """CREATE TABLE IF NOT EXISTS mu_chat_sessions (
        id         TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        title      TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_sessions_user ON mu_chat_sessions(user_id, updated_at DESC)",
    # 聊天消息（持久化，修复原版重启丢失问题）
    """CREATE TABLE IF NOT EXISTS mu_chat_messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT NOT NULL,
        user_id     INTEGER NOT NULL,
        role        TEXT NOT NULL,
        content     TEXT NOT NULL,
        model_name  TEXT,
        token_stats TEXT,
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_msg_session ON mu_chat_messages(session_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_mu_msg_user ON mu_chat_messages(user_id)",
    # 记忆
    """CREATE TABLE IF NOT EXISTS mu_memories (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        type         TEXT NOT NULL,
        content      TEXT NOT NULL,
        keywords     TEXT,
        session_id   TEXT,
        weight       REAL DEFAULT 1.0,
        access_count INTEGER DEFAULT 0,
        timestamp    TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_mem_user ON mu_memories(user_id, type)",
    # 脚本
    """CREATE TABLE IF NOT EXISTS mu_scripts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        name         TEXT NOT NULL,
        code         TEXT NOT NULL,
        description  TEXT DEFAULT '',
        is_approved  INTEGER DEFAULT 0,
        approved_at  TEXT,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_scripts_user ON mu_scripts(user_id)",
    # Cron 任务/运行记录（字段对齐 cron.db + user_id）
    """CREATE TABLE IF NOT EXISTS mu_cron_tasks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        name       TEXT NOT NULL,
        task_type  TEXT NOT NULL,
        content    TEXT NOT NULL,
        schedule   TEXT,
        run_at     TEXT,
        enabled    INTEGER DEFAULT 1,
        timeout    INTEGER DEFAULT 300,
        session_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        next_run_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_cron_user ON mu_cron_tasks(user_id, enabled)",
    """CREATE TABLE IF NOT EXISTS mu_cron_runs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     INTEGER NOT NULL,
        user_id     INTEGER NOT NULL,
        status      TEXT NOT NULL,
        output      TEXT,
        error       TEXT,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        duration    REAL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_runs_task ON mu_cron_runs(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_mu_runs_user ON mu_cron_runs(user_id)",
    # Agent 系统（落库替代内存全局列表）
    """CREATE TABLE IF NOT EXISTS mu_agents (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id          INTEGER NOT NULL,
        name             TEXT NOT NULL,
        role_description TEXT DEFAULT '',
        avatar           TEXT DEFAULT '🤖',
        tone             TEXT DEFAULT '',
        model_id         TEXT,
        model_name       TEXT,
        model_type       TEXT DEFAULT 'text',
        capabilities     TEXT DEFAULT '[]',
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_agents_user ON mu_agents(user_id)",
    """CREATE TABLE IF NOT EXISTS mu_agent_memories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        agent_id    INTEGER NOT NULL,
        content     TEXT NOT NULL,
        source      TEXT DEFAULT 'manual',
        created_at  TEXT NOT NULL,
        FOREIGN KEY (agent_id) REFERENCES mu_agents(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_agent_mem ON mu_agent_memories(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_mu_agent_mem_user ON mu_agent_memories(user_id)",
    # Agent 长期计划（目标→步骤→进度，user_id 隔离）
    """CREATE TABLE IF NOT EXISTS mu_agent_plans (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        agent_id   INTEGER NOT NULL,
        title      TEXT NOT NULL,
        steps      TEXT NOT NULL DEFAULT '[]',
        status     TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_plans_agent ON mu_agent_plans(agent_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_mu_plans_user ON mu_agent_plans(user_id)",
    # 知识库
    """CREATE TABLE IF NOT EXISTS mu_knowledge_docs (
        id          TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL,
        filename    TEXT NOT NULL,
        file_size   INTEGER,
        chunk_count INTEGER DEFAULT 0,
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_kb_user ON mu_knowledge_docs(user_id)",
    """CREATE TABLE IF NOT EXISTS mu_knowledge_vectors (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        doc_id      TEXT NOT NULL,
        chunk_index INTEGER,
        content     TEXT,
        vector      TEXT,
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_vec_doc ON mu_knowledge_vectors(doc_id)",
    "CREATE INDEX IF NOT EXISTS idx_mu_vec_user ON mu_knowledge_vectors(user_id)",
    # 操作日志（安全审计 + history 端点数据源）
    """CREATE TABLE IF NOT EXISTS mu_operation_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        operation  TEXT,
        detail     TEXT,
        success    INTEGER DEFAULT 1,
        ip         TEXT,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_logs_user ON mu_operation_logs(user_id, created_at DESC)",
    # MCP server 配置（user_id 隔离）
    """CREATE TABLE IF NOT EXISTS mu_mcp_servers (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        name       TEXT NOT NULL,
        transport  TEXT NOT NULL DEFAULT 'stdio',
        command    TEXT DEFAULT '',
        args       TEXT DEFAULT '[]',
        env        TEXT DEFAULT '{}',
        url        TEXT DEFAULT '',
        enabled    INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_mcp_user ON mu_mcp_servers(user_id, enabled)",
    # 会话上下文压缩摘要（user_id 隔离，每会话一条）
    """CREATE TABLE IF NOT EXISTS mu_session_summaries (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id          INTEGER NOT NULL,
        session_id       TEXT NOT NULL,
        summary          TEXT NOT NULL,
        covered_until_id INTEGER NOT NULL DEFAULT 0,
        updated_at       TEXT NOT NULL,
        UNIQUE(session_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_summary_user ON mu_session_summaries(user_id, session_id)",
]

# 已有库的列迁移：mu_agents 新增人格化字段（avatar/tone），mu_agent_memories 新增来源
_AGENT_MIGRATION_COLUMNS = [
    ("avatar", "TEXT DEFAULT '🤖'"),
    ("tone", "TEXT DEFAULT ''"),
    ("capabilities", "TEXT DEFAULT '[]'"),
]

_MEMO_MIGRATION_COLUMNS = [
    ("source", "TEXT DEFAULT 'manual'"),
]


def get_conn() -> sqlite3.Connection:
    """获取新连接（短连接模式，WAL 下读写不互斥）"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    """初始化数据库：建库 + 全部 DDL + 已有库列迁移"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    try:
        for ddl in DDL:
            conn.execute(ddl)
        # 已有库迁移：mu_agents / mu_agent_memories 缺失列补齐
        for table, cols in (("mu_agents", _AGENT_MIGRATION_COLUMNS),
                            ("mu_agent_memories", _MEMO_MIGRATION_COLUMNS)):
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col, coldef in cols:
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
        conn.commit()
    finally:
        conn.close()


def check_wal() -> str:
    conn = get_conn()
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
