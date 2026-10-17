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
        last_login_at TEXT,
        last_login_device TEXT DEFAULT '',
        totp_secret   TEXT    DEFAULT '',
        totp_enabled  INTEGER NOT NULL DEFAULT 0
    )""",
    # 用户表索引：登录按 username、列表按 created_at 排序、活跃度查询
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
    "CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_users_last_login ON users(last_login_at)",
    # 聊天会话
    """CREATE TABLE IF NOT EXISTS mu_chat_sessions (
        id         TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        title      TEXT DEFAULT '',
        starred    INTEGER NOT NULL DEFAULT 0,
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
    # role 索引：usage-ranking 按 role='assistant' 聚合，避免随消息增长退化为全表扫描
    "CREATE INDEX IF NOT EXISTS idx_mu_msg_role ON mu_chat_messages(role)",
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
        stored_name TEXT DEFAULT '',
        file_size   INTEGER,
        chunk_count INTEGER DEFAULT 0,
        content_hash TEXT DEFAULT '',
        is_public   INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_kb_user ON mu_knowledge_docs(user_id)",
    # 注意：idx_mu_kb_public 索引在迁移补列后单独创建（旧库需先 ALTER 才有 is_public 列）
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
    # 知识库共享内容（内容寻址：相同文件内容全局只存一次，多用户共享）
    """CREATE TABLE IF NOT EXISTS kb_content (
        content_hash TEXT PRIMARY KEY,
        filename     TEXT NOT NULL,
        file_size    INTEGER,
        chunk_count  INTEGER DEFAULT 0,
        created_at   TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS kb_content_vectors (
        content_hash TEXT NOT NULL,
        chunk_index  INTEGER,
        content      TEXT,
        vector       TEXT,
        PRIMARY KEY (content_hash, chunk_index)
    )""",
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
        headers    TEXT DEFAULT '{}',
        enabled    INTEGER DEFAULT 1,
        is_public  INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_mcp_user ON mu_mcp_servers(user_id, enabled)",
    # MCP 服务端：配置化 API 封装工具（user_id 隔离）
    """CREATE TABLE IF NOT EXISTS mu_mcp_tools (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER NOT NULL,
        name          TEXT NOT NULL,
        description   TEXT DEFAULT '',
        url           TEXT NOT NULL,
        method        TEXT NOT NULL DEFAULT 'GET',
        headers       TEXT DEFAULT '{}',
        query_params  TEXT DEFAULT '{}',
        body_template TEXT DEFAULT '',
        params_schema TEXT DEFAULT '[]',
        timeout       INTEGER DEFAULT 30,
        enabled       INTEGER DEFAULT 1,
        is_public     INTEGER DEFAULT 0,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        UNIQUE(user_id, name)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_mcp_tools_user ON mu_mcp_tools(user_id, enabled)",
    # MCP 服务端：每用户访问令牌（仅存 sha256，不存明文）
    """CREATE TABLE IF NOT EXISTS mu_mcp_tokens (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        name         TEXT DEFAULT '',
        token_hash   TEXT UNIQUE NOT NULL,
        prefix       TEXT DEFAULT '',
        revoked      INTEGER DEFAULT 0,
        last_used_at TEXT,
        expires_at   TEXT DEFAULT '',
        created_at   TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_mcp_tokens_user ON mu_mcp_tokens(user_id, revoked)",
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
    # 接口访问日志（记录所有 /api/lobster-mu 请求，仅管理员可查）
    """CREATE TABLE IF NOT EXISTS mu_api_access_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        method      TEXT NOT NULL,
        path        TEXT NOT NULL,
        status      INTEGER NOT NULL,
        duration_ms INTEGER DEFAULT 0,
        ip          TEXT DEFAULT '',
        username    TEXT DEFAULT '',
        user_id     INTEGER DEFAULT 0,
        auth_type   TEXT DEFAULT '',
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_api_logs_user ON mu_api_access_logs(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mu_api_logs_path ON mu_api_access_logs(path)",
    "CREATE INDEX IF NOT EXISTS idx_mu_api_logs_time ON mu_api_access_logs(created_at DESC)",
    # 用户建议（非管理员向管理员提建议，管理员可查看/回复/删除）
    """CREATE TABLE IF NOT EXISTS mu_suggestions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        username    TEXT NOT NULL DEFAULT '',
        content     TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'pending',
        reply       TEXT,
        replied_by  INTEGER,
        replied_at  TEXT,
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_sug_user ON mu_suggestions(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mu_sug_status ON mu_suggestions(status, created_at DESC)",
    # 多用户技能（Skill）：user_id=0 且 is_public=1 表示管理员发布的公共技能
    """CREATE TABLE IF NOT EXISTS mu_skills (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL DEFAULT 0,
        skill_id    TEXT NOT NULL UNIQUE,
        name        TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        skill_type  TEXT NOT NULL DEFAULT 'custom',
        executor    TEXT NOT NULL DEFAULT 'llm',
        enabled     INTEGER NOT NULL DEFAULT 1,
        is_public   INTEGER NOT NULL DEFAULT 0,
        config_json TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_skills_user ON mu_skills(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_mu_skills_public ON mu_skills(is_public)",
    # 用户文件库（上传文件的元数据 + 解析文本，user_id 隔离，可在会话中复用）
    """CREATE TABLE IF NOT EXISTS mu_files (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        filename    TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        file_size   INTEGER DEFAULT 0,
        content     TEXT,
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mu_files_user ON mu_files(user_id, id DESC)",
    # 系统配置键值表（管理员可在界面调整的全局开关/阈值）
    """CREATE TABLE IF NOT EXISTS mu_config (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
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

_USER_MIGRATION_COLUMNS = [
    ("totp_secret", "TEXT DEFAULT ''"),
    ("totp_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("last_login_device", "TEXT DEFAULT ''"),
]

_KB_DOCS_MIGRATION_COLUMNS = [
    ("content_hash", "TEXT DEFAULT ''"),
    ("stored_name", "TEXT DEFAULT ''"),
    # 公共知识库：is_public=1 表示管理员发布的公共文档，所有用户检索可命中（user_id 保留原作者）
    ("is_public", "INTEGER NOT NULL DEFAULT 0"),
]

_SESSION_MIGRATION_COLUMNS = [
    ("starred", "INTEGER NOT NULL DEFAULT 0"),
]

_MCP_SERVERS_MIGRATION_COLUMNS = [
    # MCP client 连接外部 server 时的自定义请求头（如 Authorization: Bearer ...）
    ("headers", "TEXT DEFAULT '{}'"),
    # server 是否公共（公共 server 所有用户 chat 时可调用）
    ("is_public", "INTEGER DEFAULT 0"),
]

_MCP_TOOLS_MIGRATION_COLUMNS = [
    # 工具是否公共（公共工具所有用户可通过 MCP 服务端调用）
    ("is_public", "INTEGER DEFAULT 0"),
]


def get_conn() -> sqlite3.Connection:
    """获取新连接（短连接模式，WAL 下读写不互斥）。

    注意：journal_mode=WAL 是持久化属性（写入 db 文件头），在 init_db 中设置一次即可，
    这里不再重复执行该 PRAGMA——它会抢文件锁，高并发下反而成为瓶颈。
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # synchronous=NORMAL 在 WAL 下既安全又快；busy_timeout 让写锁等待而非立即报错
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def get_config(key: str, default=None):
    """读取 mu_config 配置项（不存在返回 default）"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM mu_config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_config(key: str, value) -> None:
    """写入 mu_config 配置项（upsert）"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO mu_config(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        conn.commit()
    finally:
        conn.close()


def init_db():
    """初始化数据库：建库 + 全部 DDL + 已有库列迁移"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        # WAL 是持久化属性，在这里设置一次即可（get_conn 不再重复设置以免抢锁）
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # 自动 checkpoint 阈值（页），防止 WAL 文件无限增长拖慢读取
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        for ddl in DDL:
            conn.execute(ddl)
        # 已有库迁移：users / mu_agents / mu_agent_memories 缺失列补齐
        for table, cols in (("users", _USER_MIGRATION_COLUMNS),
                            ("mu_agents", _AGENT_MIGRATION_COLUMNS),
                            ("mu_agent_memories", _MEMO_MIGRATION_COLUMNS),
                            ("mu_knowledge_docs", _KB_DOCS_MIGRATION_COLUMNS),
                            ("mu_chat_sessions", _SESSION_MIGRATION_COLUMNS),
                            ("mu_mcp_servers", _MCP_SERVERS_MIGRATION_COLUMNS),
                            ("mu_mcp_tools", _MCP_TOOLS_MIGRATION_COLUMNS)):
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col, coldef in cols:
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
        # 迁移补列后才能创建的索引（依赖 is_public 等新列）
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mu_kb_public ON mu_knowledge_docs(is_public)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mu_mcp_tools_public ON mu_mcp_tools(is_public, enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mu_mcp_servers_public ON mu_mcp_servers(is_public, enabled)")
        # 更新统计信息，帮助查询优化器选择正确计划（数据量增长后尤其重要）
        try:
            conn.execute("ANALYZE")
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()


def db_maintenance() -> dict:
    """数据库维护：checkpoint 回收 WAL、VACUUM 回收空闲页、ANALYZE 更新统计。

    用于「随时间变慢」的手动修复——删除大字段（如向量）留下的空闲页会让库文件
    膨胀，VACUUM 重建库文件可显著缩小体积并提升页读取速度。
    返回维护前后的文件大小信息。
    """
    import os as _os
    before = _os.path.getsize(DB_PATH) if _os.path.exists(DB_PATH) else 0
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
    finally:
        conn.close()
    after = _os.path.getsize(DB_PATH) if _os.path.exists(DB_PATH) else 0
    return {"before_bytes": before, "after_bytes": after,
            "freed_bytes": before - after}


def check_wal() -> str:
    conn = get_conn()
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
