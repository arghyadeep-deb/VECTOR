
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from loguru import logger
import asyncio, uuid, json, sqlite3, datetime

class EpisodicMemory:
    def __init__(self):
        self.conn = sqlite3.connect(CONFIG['db_path'])
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        logger.info("Episodic memory initialized with DB connection")
    
    def _create_tables(self):
        tables = [
            """CREATE TABLE IF NOT EXISTS episodic_memory (
                id TEXT PRIMARY KEY,
                event_type TEXT,
                content TEXT,
                tags TEXT,
                context_snapshot TEXT,
                timestamp TEXT,
                source TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS semantic_memory (
                key TEXT PRIMARY KEY,
                value TEXT,
                category TEXT,
                confidence REAL DEFAULT 0.5,
                updated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS policy_memory (
                action_type TEXT,
                situation_hash TEXT,
                avg_reward REAL,
                sample_count INTEGER DEFAULT 0,
                last_updated TEXT,
                PRIMARY KEY (action_type, situation_hash)
            )""",
            """CREATE TABLE IF NOT EXISTS reasoning_chains (
                chain_id TEXT PRIMARY KEY,
                situation TEXT,
                goal_ids TEXT,
                steps TEXT,
                action_taken TEXT,
                outcome TEXT,
                reward REAL DEFAULT 0.0,
                is_training_data INTEGER DEFAULT 0,
                timestamp TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS skill_memory (
                skill_name TEXT PRIMARY KEY,
                confidence REAL DEFAULT 0.5,
                last_practiced TEXT,
                evidence TEXT,
                related_skills TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS agent_history (
                agent_id TEXT,
                agent_name TEXT,
                district TEXT,
                generation INTEGER,
                final_hp INTEGER,
                ghost_memory TEXT,
                died_at TEXT,
                PRIMARY KEY (agent_id, generation)
            )"""
        ]
        for table in tables:
            try:
                self.conn.execute(table)
            except sqlite3.OperationalError as e:
                logger.error(f"Table creation failed: {e}")
    
    def store(self, event_type, content, tags=None, context=None, source='vector') -> str:
        try:
            id = str(uuid.uuid4())
            tags_json = json.dumps(tags) if tags else None
            context_json = json.dumps(context) if context else None
            timestamp = datetime.datetime.now().isoformat()
            
            self.conn.execute("""
                INSERT INTO episodic_memory
                (id, event_type, content, tags, context_snapshot, timestamp, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (id, event_type, content, tags_json, context_json, timestamp, source))
            self.conn.commit()
            return id
        except Exception as e:
            logger.error(f"Store failed: {e}")
            return ""
    
    def recall(self, query, limit=5, event_type=None) -> list[dict]:
        try:
            cursor = self.conn.cursor()
            query = f"%{query}%"
            conditions = [f"content LIKE ?", f"event_type = ?"] if event_type else [f"content LIKE ?"]
            params = [query] + (event_type and [event_type] or [])
            
            cursor.execute(f"""
                SELECT * FROM episodic_memory
                WHERE {' AND '.join(conditions)}
                ORDER BY timestamp DESC
                LIMIT ?
            """, params + [limit])
            
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return results
        except Exception as e:
            logger.error(f"Recall failed: {e}")
            return []
    
    def remember(self, key, value, category='general', confidence=0.5) -> bool:
        try:
            updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.conn.execute("""
                INSERT INTO semantic_memory (key, value, category, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    category=excluded.category,
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
            """, (key, value, category, confidence, updated_at))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Remember failed: {e}")
            return False
    
    def recall_fact(self, key) -> dict | None:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM semantic_memory
                WHERE key = ?
            """, (key,))
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logger.error(f"Recall fact failed: {e}")
            return None
    
    def store_chain(self, situation, goal_ids, steps, action, outcome, reward) -> str:
        try:
            chain_id = str(uuid.uuid4())
            goal_ids_json = json.dumps(goal_ids)
            steps_json = json.dumps(steps)
            is_training = 1 if reward > 0.7 else 0
            timestamp = datetime.datetime.now().isoformat()
            
            self.conn.execute("""
                INSERT INTO reasoning_chains
                (chain_id, situation, goal_ids, steps, action_taken, outcome, reward, is_training_data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (chain_id, situation, goal_ids_json, steps_json, action, outcome, reward, is_training, timestamp))
            self.conn.commit()
            return chain_id
        except Exception as e:
            logger.error(f"Store chain failed: {e}")
            return ""
    
    def get_training_data(self, limit=100) -> list[dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM reasoning_chains
                WHERE is_training_data = 1
                ORDER BY reward DESC
                LIMIT ?
            """, (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Get training data failed: {e}")
            return []
    
    def update_skill(self, skill_name, confidence, evidence=None) -> bool:
        try:
            evidence_json = json.dumps(evidence) if evidence else None
            self.conn.execute("""
                INSERT INTO skill_memory (skill_name, confidence, evidence)
                VALUES (?, ?, ?)
                ON CONFLICT(skill_name) DO UPDATE SET
                    confidence=excluded.confidence,
                    evidence=COALESCE(excluded.evidence, skill_memory.evidence)
            """, (skill_name, confidence, evidence_json))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Update skill failed: {e}")
            return False
    
    def get_skill(self, skill_name) -> dict | None:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM skill_memory
                WHERE skill_name = ?
            """, (skill_name,))
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logger.error(f"Get skill failed: {e}")
            return None
    
    def get_stats(self) -> dict:
        _TABLES = ("episodic_memory", "semantic_memory", "policy_memory",
                   "reasoning_chains", "skill_memory", "agent_history")
        try:
            stats = {}
            for table in _TABLES:
                cursor = self.conn.cursor()
                # Table name comes from a closed constant — not user input — so f-string is safe.
                # SQLite doesn't support parameterised identifiers, so we use the constant directly.
                cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                stats[table] = cursor.fetchone()[0]
            return stats
        except Exception as e:
            logger.error(f"Get stats failed: {e}")
            return {}
    
    def close(self):
        self.conn.close()
        logger.info("Episodic memory connection closed")

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding="utf-8")
    mem = EpisodicMemory()
    id1 = mem.store('test', 'VECTOR started for first time', ['init','test'])
    id2 = mem.store('task', 'Checked KIIT attendance', ['kiit','attendance'])
    results = mem.recall('KIIT')
    assert len(results) >= 1, 'recall failed'
    mem.remember('owner_name', 'Arghyadeep', 'identity', 1.0)
    fact = mem.recall_fact('owner_name')
    assert fact is not None, 'recall_fact failed'
    chain_id = mem.store_chain('exam tomorrow', ['study'], ['opened notes','read chapter'], 'set reminder', 'reminder set', 0.9)
    training = mem.get_training_data()
    assert len(training) >= 1, 'training data failed'
    stats = mem.get_stats()
    mem.close()
    print(f"✅ episodic.py OK — {stats}")
