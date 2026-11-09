import sqlite3
import os
from datetime import datetime


class ScriptManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'data', 'scripts.db')
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()

    def _create_tables(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_approved INTEGER DEFAULT 0,
                approved_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_scripts_name ON scripts(name)
        ''')
        conn.commit()
        conn.close()

    def create_script(self, name, code, description="", is_approved=False):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scripts (name, code, description, is_approved, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, code, description, 1 if is_approved else 0, now, now))
        script_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return self.get_script(script_id)

    def get_script(self, script_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM scripts WHERE id = ?', (script_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return self._row_to_dict(row)
        return None

    def list_scripts(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM scripts ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def update_script(self, script_id, name=None, code=None, description=None):
        script = self.get_script(script_id)
        if not script:
            return None
        
        now = datetime.now().isoformat()
        name = name if name is not None else script['name']
        code = code if code is not None else script['code']
        description = description if description is not None else script['description']
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE scripts SET name = ?, code = ?, description = ?, updated_at = ?
            WHERE id = ?
        ''', (name, code, description, now, script_id))
        conn.commit()
        conn.close()
        return self.get_script(script_id)

    def delete_script(self, script_id):
        script = self.get_script(script_id)
        if not script:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM scripts WHERE id = ?', (script_id,))
        conn.commit()
        conn.close()
        return True

    def approve_script(self, script_id):
        script = self.get_script(script_id)
        if not script:
            return None
        
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE scripts SET is_approved = 1, approved_at = ?, updated_at = ?
            WHERE id = ?
        ''', (now, now, script_id))
        conn.commit()
        conn.close()
        return self.get_script(script_id)

    def revoke_script(self, script_id):
        script = self.get_script(script_id)
        if not script:
            return None
        
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE scripts SET is_approved = 0, approved_at = NULL, updated_at = ?
            WHERE id = ?
        ''', (now, script_id))
        conn.commit()
        conn.close()
        return self.get_script(script_id)

    def _row_to_dict(self, row):
        return {
            'id': row[0],
            'name': row[1],
            'code': row[2],
            'description': row[3],
            'is_approved': bool(row[4]),
            'approved_at': row[5],
            'created_at': row[6],
            'updated_at': row[7]
        }


script_manager = ScriptManager()
