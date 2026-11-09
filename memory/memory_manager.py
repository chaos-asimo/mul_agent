import sqlite3
import os
import re
from datetime import datetime, timedelta


class MemoryManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'memory.db')
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()

    def _create_tables(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                keywords TEXT,
                session_id TEXT,
                timestamp DATETIME NOT NULL,
                weight REAL DEFAULT 1.0,
                access_count INTEGER DEFAULT 0
            )
        ''')
        # 兼容旧数据库：自动添加缺失的列
        cursor.execute("PRAGMA table_info(memories)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if 'weight' not in existing_columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN weight REAL DEFAULT 1.0")
        if 'access_count' not in existing_columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN access_count INTEGER DEFAULT 0")
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id)
        ''')
        conn.commit()
        conn.close()

    def store(self, memory_type, content, keywords=None, session_id=None, weight=1.0):
        if memory_type not in ('instant', 'short_term', 'long_term'):
            raise ValueError("memory_type must be 'instant', 'short_term', or 'long_term'")
        
        existing_memory = self._find_similar_memory(content, memory_type)
        if existing_memory:
            self._update_memory_weight(existing_memory['id'], weight)
            return existing_memory['id']
        
        keywords_str = ','.join(keywords) if keywords else None
        timestamp = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO memories (type, content, keywords, session_id, timestamp, weight, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (memory_type, content, keywords_str, session_id, timestamp, weight, 0))
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return memory_id

    def _find_similar_memory(self, content, memory_type, threshold=0.7):
        keywords = self.extract_keywords(content, max_keywords=5)
        if not keywords:
            return None
        
        for keyword in keywords:
            results = self.retrieve(keyword, memory_type, limit=3)
            for result in results:
                similarity = self._calculate_similarity(content, result['content'])
                if similarity >= threshold:
                    return result
        return None

    def _calculate_similarity(self, text1, text2):
        if not text1 or not text2:
            return 0.0
        # 使用关键词提取来构建词集合（兼容中英文）
        words1 = set(self.extract_keywords(text1, max_keywords=20))
        words2 = set(self.extract_keywords(text2, max_keywords=20))
        # 补充英文按空格分词
        words1.update(w.lower() for w in text1.split() if len(w) > 1)
        words2.update(w.lower() for w in text2.split() if len(w) > 1)
        if not words1 and not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0

    def _update_memory_weight(self, memory_id, weight_increment=0.5):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE memories SET weight = weight + ?, access_count = access_count + 1, timestamp = ?
            WHERE id = ?
        ''', (weight_increment, datetime.now().isoformat(), memory_id))
        conn.commit()
        conn.close()

    def retrieve(self, query=None, memory_type=None, limit=10, days=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        query_params = []
        where_clauses = []

        if memory_type:
            where_clauses.append('type = ?')
            query_params.append(memory_type)

        if days:
            cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
            where_clauses.append('timestamp >= ?')
            query_params.append(cutoff_time)

        if query:
            where_clauses.append('(content LIKE ? OR keywords LIKE ?)')
            query_pattern = f'%{query}%'
            query_params.extend([query_pattern, query_pattern])

        query_str = 'SELECT * FROM memories'
        if where_clauses:
            query_str += ' WHERE ' + ' AND '.join(where_clauses)
        
        query_str += ' ORDER BY (weight * 0.7 + access_count * 0.3) DESC, timestamp DESC LIMIT ?'
        query_params.append(limit)

        cursor.execute(query_str, query_params)
        rows = cursor.fetchall()
        conn.close()

        results = self._rows_to_dicts(rows)
        
        for result in results:
            self._update_memory_weight(result['id'], 0.1)
        
        if query:
            results = self._score_results(results, query)
        
        return results

    def retrieve_by_keywords(self, keywords, memory_type=None, limit=10):
        if not keywords:
            return []
        results = []
        per_keyword_limit = max(1, limit // len(keywords))
        for keyword in keywords[:5]:
            keyword_results = self.retrieve(keyword, memory_type, per_keyword_limit)
            results.extend(keyword_results)

        seen_ids = set()
        unique_results = []
        for r in results:
            if r['id'] not in seen_ids:
                seen_ids.add(r['id'])
                unique_results.append(r)

        return unique_results[:limit]

    def _score_results(self, results, query):
        scored = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for result in results:
            score = 0
            content_lower = result['content'].lower()
            
            if query_lower in content_lower:
                score += 5
            for word in query_words:
                if word in content_lower:
                    score += 2
            
            keywords = result.get('keywords', [])
            for kw in keywords:
                if kw.lower() in query_lower:
                    score += 3
            
            result['score'] = score
            scored.append(result)
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored

    def extract_keywords(self, text, max_keywords=5):
        if not text or not text.strip():
            return []
        original_text = text
        text = text.lower()
        text = re.sub(r'[^\w\s\u4e00-\u9fa5]', ' ', text)

        stop_words = {'的', '了', '和', '是', '就', '都', '而', '及', '与', '着', '或', '一个', '没有', '我们', '你们', '他们', '这', '那', '什么', '怎么', '为什么', '因为', '所以', '但是', '如果', '可以', '能', '会', '应该', '需要', '可能', '已经', '正在', '将要', '曾经', '不', '很', '也', '还', '又', '再', '更', '最', '太', '非常', '特别', '以及', '等等', '通过', '根据', '按照', '关于', '对于', '至于', '由于', '鉴于', '为了', '以便', '以免', '否则', '要么', '或者', '无论', '不管', '尽管', '即使', '假如', '倘若', '万一', '要是', '只要', '只有', '除非', '一旦', '既然', 'when', 'what', 'how', 'why', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'all', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now', 'out', 'up', 'down', 'off', 'over'}

        candidates = []

        # 在中英文/数字边界插入空格，便于英文词提取
        text_for_split = re.sub(r'([\u4e00-\u9fa5])([a-z0-9])', r'\1 \2', text)
        text_for_split = re.sub(r'([a-z0-9])([\u4e00-\u9fa5])', r'\1 \2', text_for_split)

        # 英文/数字词（按空格分词）
        for word in text_for_split.split():
            if len(word) > 1 and word not in stop_words and not word.isdigit():
                candidates.append(word)

        # 中文 n-gram 分词（2-4字），在没有空格的中文段落中提取候选词
        chinese_segments = re.findall(r'[\u4e00-\u9fa5]+', original_text)
        for seg in chinese_segments:
            seg = seg.strip()
            if len(seg) <= 1:
                continue
            # 整段就是单字或双字，直接作为候选
            if len(seg) <= 3:
                if seg not in stop_words:
                    candidates.append(seg)
                continue
            # 长段落使用 2-gram 和 3-gram 提取，避免整句作为关键词
            for n in (2, 3):
                if len(seg) < n:
                    continue
                for i in range(len(seg) - n + 1):
                    gram = seg[i:i + n]
                    if gram in stop_words:
                        continue
                    candidates.append(gram)

        word_counts = {}
        for word in candidates:
            word_counts[word] = word_counts.get(word, 0) + 1

        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:max_keywords]]

    def delete(self, memory_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM memories WHERE id = ?', (memory_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def get_all(self, memory_type=None, limit=100):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        query_params = []

        if memory_type:
            query_str = 'SELECT * FROM memories WHERE type = ? ORDER BY timestamp DESC LIMIT ?'
            query_params = [memory_type, limit]
        else:
            query_str = 'SELECT * FROM memories ORDER BY timestamp DESC LIMIT ?'
            query_params = [limit]

        cursor.execute(query_str, query_params)
        rows = cursor.fetchall()
        conn.close()

        return self._rows_to_dicts(rows)

    def clear(self, memory_type):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM memories WHERE type = ?', (memory_type,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected

    def _rows_to_dicts(self, rows):
        result = []
        for row in rows:
            memory = {
                'id': row[0],
                'type': row[1],
                'content': row[2],
                'keywords': row[3].split(',') if row[3] else [],
                'session_id': row[4],
                'timestamp': row[5],
                'weight': row[6] if len(row) > 6 else 1.0,
                'access_count': row[7] if len(row) > 7 else 0
            }
            result.append(memory)
        return result