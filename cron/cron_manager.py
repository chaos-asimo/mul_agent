import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


class CronTaskManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'cron.db')
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()

    def _create_tables(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cron_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                content TEXT NOT NULL,
                schedule TEXT,
                run_at TEXT,
                enabled INTEGER DEFAULT 1,
                timeout INTEGER DEFAULT 300,
                session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                next_run_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cron_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                output TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration REAL,
                FOREIGN KEY (task_id) REFERENCES cron_tasks(id)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cron_tasks_enabled ON cron_tasks(enabled)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cron_tasks_next_run ON cron_tasks(next_run_at)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cron_runs_task ON cron_runs(task_id)
        ''')
        conn.commit()
        conn.close()

    def add_task(self, name: str, task_type: str, content: str,
                schedule: Optional[str] = None, run_at: Optional[str] = None,
                enabled: bool = True, timeout: int = 300, session_id: Optional[str] = None) -> int:
        timestamp = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cron_tasks (name, task_type, content, schedule, run_at, 
                                    enabled, timeout, session_id, created_at, updated_at, next_run_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, task_type, content, schedule, run_at, 1 if enabled else 0,
              timeout, session_id, timestamp, timestamp, None))
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cron_tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def list_tasks(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if enabled is not None:
            cursor.execute('SELECT * FROM cron_tasks WHERE enabled = ? ORDER BY updated_at DESC',
                          (1 if enabled else 0,))
        else:
            cursor.execute('SELECT * FROM cron_tasks ORDER BY updated_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def update_task(self, task_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        kwargs['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f'{k} = ?' for k in kwargs.keys())
        params = list(kwargs.values()) + [task_id]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f'UPDATE cron_tasks SET {set_clause} WHERE id = ?', params)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def delete_task(self, task_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cron_runs WHERE task_id = ?', (task_id,))
        cursor.execute('DELETE FROM cron_tasks WHERE id = ?', (task_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def toggle_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT enabled FROM cron_tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        new_enabled = 0 if row[0] == 1 else 1
        cursor.execute('UPDATE cron_tasks SET enabled = ?, updated_at = ? WHERE id = ?',
                      (new_enabled, datetime.now().isoformat(), task_id))
        conn.commit()
        cursor.execute('SELECT * FROM cron_tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def add_run(self, task_id: int, status: str, output: str = '',
                error: str = '', started_at: str = None, finished_at: str = None,
                duration: float = 0.0):
        if started_at is None:
            started_at = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cron_runs (task_id, status, output, error, started_at, finished_at, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, status, output, error, started_at, finished_at, duration))
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def update_run(self, run_id: int, **kwargs):
        if not kwargs:
            return False
        set_clause = ', '.join(f'{k} = ?' for k in kwargs.keys())
        params = list(kwargs.values()) + [run_id]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f'UPDATE cron_runs SET {set_clause} WHERE id = ?', params)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def get_runs(self, task_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM cron_runs WHERE task_id = ? ORDER BY started_at DESC LIMIT ?
        ''', (task_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [self._run_row_to_dict(row) for row in rows]

    def get_due_tasks(self) -> List[Dict[str, Any]]:
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM cron_tasks 
            WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?)
            ORDER BY next_run_at ASC
        ''', (now,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row) -> Dict[str, Any]:
        return {
            'id': row[0],
            'name': row[1],
            'task_type': row[2],
            'content': row[3],
            'schedule': row[4],
            'run_at': row[5],
            'enabled': row[6] == 1,
            'timeout': row[7],
            'session_id': row[8],
            'created_at': row[9],
            'updated_at': row[10],
            'next_run_at': row[11]
        }

    def _run_row_to_dict(self, row) -> Dict[str, Any]:
        return {
            'id': row[0],
            'task_id': row[1],
            'status': row[2],
            'output': row[3],
            'error': row[4],
            'started_at': row[5],
            'finished_at': row[6],
            'duration': row[7]
        }
