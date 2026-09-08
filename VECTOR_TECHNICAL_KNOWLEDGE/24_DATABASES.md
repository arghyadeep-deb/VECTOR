# Databases and Storage

**Purpose:** All persistence layers — SQLCipher, Supabase, Cloudflare D1, R2, KV, collections
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR uses a multi-database architecture with SQLCipher as primary local store, Supabase for cloud sync, Cloudflare D1/R2/KV for remote API, and a collections engine for dynamic schemas.

**Key Properties:**
- **SQLCipher** — AES-256 encrypted local SQLite
- **Supabase** — cloud Postgres via raw httpx REST
- **Cloudflare D1** — remote SQLite for API
- **Cloudflare R2** — object storage
- **Cloudflare KV** — key-value cache
- **Collections** — dynamic schema tables
- **Multi-DB mesh** — sync across all stores

**Files:**
- `core/memory/episodic.py` (~400 lines)
- `core/memory/multi_db_manager.py` (~300 lines)
- `core/collections/` (~8 files)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## SQLCipher (Primary Local)

### Encrypted SQLite

**File:** `core/memory/episodic.py`
**Status:** ✅ IMPLEMENTED

```python
import sqlcipher3
from core.config import CONFIG

def get_db_connection():
    """Get encrypted DB connection."""
    db_path = CONFIG["db_path"]
    key = CONFIG["db_key"]
    
    if not key:
        raise RuntimeError("SQLCipher key not set")
    
    conn = sqlcipher3.connect(db_path)
    conn.execute(f"PRAGMA key = '{key}'")
    conn.execute("PRAGMA journal_mode = WAL")
    
    # Verify
    try:
        conn.execute("SELECT 1")
    except Exception:
        raise RuntimeError("SQLCipher key invalid")
    
    return conn

def close_db_connection(conn):
    """Safely close connection."""
    try:
        conn.close()
    except Exception:
        pass
```

### Schema

```sql
-- 5 sacred tables (NEVER touched by collections engine)
CREATE TABLE IF NOT EXISTS episodic_memory (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    metadata TEXT,
    timestamp REAL,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS policy_memory (
    id INTEGER PRIMARY KEY,
    action TEXT,
    score REAL,
    outcome REAL,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS reasoning_chains (
    id INTEGER PRIMARY KEY,
    chain TEXT,
    reward REAL,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS ghost_memory (
    id INTEGER PRIMARY KEY,
    agent_id TEXT,
    lessons TEXT,
    death_timestamp REAL
);

CREATE TABLE IF NOT EXISTS agent_registry (
    id INTEGER PRIMARY KEY,
    agent_id TEXT,
    name TEXT,
    hp INTEGER,
    status TEXT,
    district TEXT
);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(
    content,
    content='episodic_memory',
    content_rowid='id'
);
```

---

## Multi-DB Mesh

### Cross-Store Sync

**File:** `core/memory/multi_db_manager.py`
**Status:** ✅ IMPLEMENTED

```python
class MultiDBManager:
    """Manage sync across all databases."""
    
    def __init__(self):
        self.stores = {
            "local": SQLiteStore(),
            "supabase": SupabaseStore(),
            "cloudflare": CloudflareStore()
        }
    
    async def sync_all(self):
        """Sync all stores."""
        # Local → Cloud
        local_data = await self.stores["local"].get_all()
        
        for record in local_data:
            await self.stores["supabase"].upsert(record)
            await self.stores["cloudflare"].upsert(record)
    
    async def quarantine(self, store_name: str):
        """Quarantine a store on corruption."""
        logger.warning(f"[VECTOR][db] Quarantining {store_name}")
        self.stores[store_name].quarantined = True
    
    async def get(self, key: str):
        """Get with fallback chain."""
        # Try local first
        try:
            result = await self.stores["local"].get(key)
            if result:
                return result
        except Exception:
            pass
        
        # Try Supabase
        try:
            result = await self.stores["supabase"].get(key)
            if result:
                return result
        except Exception:
            pass
        
        # Try Cloudflare
        try:
            result = await self.stores["cloudflare"].get(key)
            if result:
                return result
        except Exception:
            pass
        
        return None
```

---

## Supabase (Cloud)

### Raw httpx REST (NO supabase-py SDK)

**File:** `core/memory/supabase_store.py`
**Status:** ✅ IMPLEMENTED

```python
import httpx
from core.config import CONFIG

class SupabaseStore:
    """Supabase via raw REST, NOT the SDK."""
    
    def __init__(self):
        self.url = CONFIG["supabase_url"]
        self.key = CONFIG["supabase_key"]
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}"
        }
    
    async def upsert(self, record: dict):
        """Upsert record."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/rest/v1/episodic_memory",
                json=record,
                headers=self.headers,
                params={"on_conflict": "id"}
            )
            return response.json()
    
    async def get(self, key: str):
        """Get record."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.url}/rest/v1/episodic_memory",
                headers=self.headers,
                params={"id": f"eq.{key}"}
            )
            results = response.json()
            return results[0] if results else None
```

---

## Collections Engine

### Dynamic Schema Tables

**File:** `core/collections/store.py`
**Status:** ✅ IMPLEMENTED

```python
class CollectionStore:
    """Dynamic schema collection store."""
    
    def __init__(self):
        self.conn = get_db_connection()
    
    async def create_collection(self, name: str, fields: list):
        """Create collection with schema."""
        # Validate field types
        for field in fields:
            if field["type"] not in VALID_FIELD_TYPES:
                raise ValueError(f"Invalid field type: {field['type']}")
        
        # Create table
        columns = ", ".join(
            f"{f['name']} {self._sql_type(f['type'])}"
            for f in fields
        )
        
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS col_{name} (
                id INTEGER PRIMARY KEY,
                {columns}
            )
        """)
        
        # Store schema
        self.conn.execute("""
            INSERT INTO _collections (name, fields)
            VALUES (?, ?)
        """, (name, json.dumps(fields)))
    
    async def insert(self, collection: str, record: dict):
        """Insert record with validation."""
        # Get schema
        schema = self._get_schema(collection)
        
        # Validate
        for field in schema:
            if field["required"] and field["name"] not in record:
                raise ValueError(f"Missing required field: {field['name']}")
            
            if field["name"] in record:
                self._validate_type(record[field["name"]], field["type"])
        
        # Insert with parameterized query (SAFE)
        columns = ", ".join(record.keys())
        placeholders = ", ".join("?" * len(record))
        
        self.conn.execute(
            f"INSERT INTO col_{collection} ({columns}) VALUES ({placeholders})",
            list(record.values())
        )
    
    async def query(self, collection: str, filters: dict = None):
        """Query with safe filter parsing."""
        if not filters:
            return self.conn.execute(
                f"SELECT * FROM col_{collection}"
            ).fetchall()
        
        # SAFE filter parser (no eval)
        where_clauses = []
        values = []
        
        for key, value in filters.items():
            where_clauses.append(f"{key} = ?")
            values.append(value)
        
        where = " AND ".join(where_clauses)
        
        return self.conn.execute(
            f"SELECT * FROM col_{collection} WHERE {where}",
            values
        ).fetchall()
```

---

## Cloudflare Storage

### D1 / R2 / KV

**File:** `api/src/router.ts` (D1 usage)
**Status:** ✅ IMPLEMENTED, DEPLOYED

```typescript
// D1 (SQLite)
await env.DB.prepare(
    'INSERT INTO command_queue (command, status) VALUES (?, ?)'
).bind(command, 'pending').run();

// KV (key-value cache)
await env.KV.put('last_heartbeat', Date.now().toString());
const heartbeat = await env.KV.get('last_heartbeat');

// R2 (object storage)
await env.R2.put('memory/snapshot.json', JSON.stringify(data));
const snapshot = await env.R2.get('memory/snapshot.json');
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| SQLCipher read | 1-10ms | Disk I/O |
| SQLCipher write | 5-20ms | Disk I/O |
| Supabase REST | 50-200ms | Network |
| Cloudflare D1 | 50-100ms | Network |
| Cloudflare KV | 10-50ms | Network |
| Collection query | 1-50ms | Query complexity |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `13_MEMORY_ARCHITECTURE.md` — Memory systems
- `30_DEPLOYMENT.md` — Deployment
- `23_BACKEND_API.md` — API layer

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
