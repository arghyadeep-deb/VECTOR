# ObsidianSync Implementation Plan

**Goal:** Bidirectional Obsidian vault bridge — VECTOR writes notes autonomously/on-demand, LightRAG graph ingests vault for context-mature semantic search.

**Architecture:** `ObsidianSync` (plain class) wraps atomic file writes + LightRAG (embedded at `agents/districts/memory_curator/lightrag/`). watchdog Observer bridges filesystem events to an asyncio Queue; async consumer debounces and feeds LightRAG. `ContextEngine.get_vault_context()` exposes LightRAG hybrid query for session hydration.

**Files:**
- Create: `core/memory/obsidian_sync.py`
- Create: `tests/test_obsidian_sync.py`
- Modify: `core/config.py` — add `obsidian` block, extend permission lists
- Modify: `core/loop/permission_gateway.py` — add `write_note_personal`, `overwrite_note_personal`
- Modify: `core/loop/context_engine.py` — add `_get_obsidian()`, `get_vault_context()`
- Modify: `core/loop/autonomous_loop.py` — add `obsidian_loop()` to `run_forever()`

---

### Task 1: CONFIG — obsidian block + permission list updates

- [ ] Edit `core/config.py` — add `obsidian` key inside `CONFIG`:
  ```python
  "obsidian": {
      "lightrag_working_dir": "./data/lightrag_vault",
      "watch_debounce_sec": 30,
      "ingest_on_startup": True,
      "protected_paths": [
          "CLAUDE.md", "GOALS.md", "VECTOR", "graphify-out", ".obsidian",
      ],
      "vector_write_folders": [
          "Daily", "Reflections", "Council", "Agent HP", "Research", "Interviews",
      ],
      "personal_write_folders": [
          "00 Notes", "01 Journals", "02 Projects", "03 Reviews", "04 Skills", "wiki",
      ],
  },
  ```
- [ ] In `VectorSettings.permission` field default, add to yellow list: `"write_note_personal"`
- [ ] In `VectorSettings.permission` field default, add to red list: `"overwrite_note_personal"`
- [ ] Run: `venv/Scripts/python core/config.py` → `✅ config.py OK`

---

### Task 2: Permission gateway — new action types

- [ ] Edit `core/loop/permission_gateway.py` — add to YELLOW list in the `_classify` logic:
  The YELLOW/RED lists come from `CONFIG["permission"]` already — Task 1's CONFIG change automatically propagates. Verify:
  ```python
  gw = PermissionGateway()
  assert gw._classify("write_note_personal") == "YELLOW"
  assert gw._classify("overwrite_note_personal") == "RED"
  ```
- [ ] Run: `venv/Scripts/python core/loop/permission_gateway.py` → `✅ permission_gateway.py OK`

---

### Task 3: Write failing tests

- [ ] Create `tests/test_obsidian_sync.py`:
  ```python
  import pytest, tempfile, os
  from pathlib import Path

  @pytest.fixture
  def tmp_vault(tmp_path):
      for folder in ["Daily", "Reflections", "00 Notes", "01 Journals"]:
          (tmp_path / folder).mkdir()
      return tmp_path

  def test_write_note_creates_file(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync
      sync = ObsidianSync(vault_path=tmp_vault)
      path = sync.write_note("Test Note", "Hello VECTOR", "Daily", ["test"])
      assert path.exists()
      assert "Hello VECTOR" in path.read_text(encoding="utf-8")

  def test_write_note_has_frontmatter(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync
      sync = ObsidianSync(vault_path=tmp_vault)
      path = sync.write_note("FM Test", "body text", "Daily", ["tag1"])
      content = path.read_text(encoding="utf-8")
      assert content.startswith("---")
      assert "source: vector" in content
      assert "tag1" in content

  def test_write_note_atomic_no_tmp(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync
      sync = ObsidianSync(vault_path=tmp_vault)
      sync.write_note("Atomic", "content", "Daily", [])
      tmp_files = list(tmp_vault.glob("**/*.tmp"))
      assert tmp_files == []

  def test_append_to_note_grows_file(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync
      sync = ObsidianSync(vault_path=tmp_vault)
      sync.write_note("Append Test", "initial", "Reflections", [])
      sync.append_to_note("Append Test", "appended block", "Reflections")
      content = (tmp_vault / "Reflections" / "Append Test.md").read_text(encoding="utf-8")
      assert "initial" in content
      assert "appended block" in content

  def test_write_note_personal_folder_raises_without_gateway(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync, PermissionDeniedError
      sync = ObsidianSync(vault_path=tmp_vault)
      with pytest.raises(PermissionDeniedError):
          sync.write_note("Journal", "text", "01 Journals", [], _bypass_gateway=False)

  def test_write_note_personal_folder_allowed_with_flag(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync
      sync = ObsidianSync(vault_path=tmp_vault)
      path = sync.write_note("Journal", "text", "01 Journals", [], _bypass_gateway=True)
      assert path.exists()

  def test_write_note_protected_path_always_raises(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync, PermissionDeniedError
      sync = ObsidianSync(vault_path=tmp_vault)
      (tmp_vault / "CLAUDE.md").write_text("protected")
      with pytest.raises(PermissionDeniedError):
          sync.write_note("CLAUDE", "evil content", ".", [], _bypass_gateway=True)

  def test_write_note_overwrite_existing_personal_raises(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync, PermissionDeniedError
      sync = ObsidianSync(vault_path=tmp_vault)
      sync.write_note("Note", "v1", "00 Notes", [], _bypass_gateway=True)
      with pytest.raises(PermissionDeniedError):
          sync.write_note("Note", "v2", "00 Notes", [], overwrite=True, _bypass_gateway=False)

  def test_is_protected_path(tmp_vault):
      from core.memory.obsidian_sync import ObsidianSync
      sync = ObsidianSync(vault_path=tmp_vault)
      assert sync._is_protected(tmp_vault / "CLAUDE.md")
      assert sync._is_protected(tmp_vault / "VECTOR" / "arch.md")
      assert not sync._is_protected(tmp_vault / "Daily" / "note.md")
  ```
- [ ] Run: `venv/Scripts/python -m pytest tests/test_obsidian_sync.py -v` → expect **FAIL** (ImportError on ObsidianSync)

---

### Task 4: Implement `core/memory/obsidian_sync.py` — write path

- [ ] Implement the module:
  ```python
  import sys, os, datetime, hashlib
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).parent.parent.parent))
  from core.config import CONFIG
  from loguru import logger

  _LIGHTRAG_PATH = Path(__file__).parent.parent.parent / "agents/districts/memory_curator"


  class PermissionDeniedError(PermissionError):
      pass


  class ObsidianSync:
      def __init__(self, vault_path: Path | None = None):
          self._vault = Path(vault_path or CONFIG["vault_path"])
          self._cfg = CONFIG.get("obsidian", {})
          self._protected = set(self._cfg.get("protected_paths", [
              "CLAUDE.md", "GOALS.md", "VECTOR", "graphify-out", ".obsidian",
          ]))
          self._vector_folders = set(self._cfg.get("vector_write_folders", [
              "Daily", "Reflections", "Council", "Agent HP", "Research", "Interviews",
          ]))
          self._personal_folders = set(self._cfg.get("personal_write_folders", [
              "00 Notes", "01 Journals", "02 Projects", "03 Reviews", "04 Skills", "wiki",
          ]))
          self._rag = None
          self._memory = None
          self._watching = False
          logger.info(f"[VECTOR][obsidian] vault={self._vault}")

      # ── Permission helpers ─────────────────────────────────────────────────

      def _is_protected(self, path: Path) -> bool:
          try:
              rel = path.relative_to(self._vault)
          except ValueError:
              return True  # outside vault = protected
          parts = rel.parts
          if not parts:
              return True
          top = parts[0]
          return top in self._protected or str(rel) in self._protected

      def _folder_level(self, folder: str) -> str:
          """Returns 'green', 'yellow', 'red_overwrite', or 'forbidden'."""
          if folder in self._vector_folders or folder == ".":
              return "green"
          if folder in self._personal_folders:
              return "yellow"
          return "forbidden"

      # ── Write path ─────────────────────────────────────────────────────────

      def write_note(
          self,
          title: str,
          content: str,
          folder: str,
          tags: list[str],
          overwrite: bool = False,
          _bypass_gateway: bool = False,
      ) -> Path:
          """
          Write a note to the vault. Atomic (tmp → rename).
          Raises PermissionDeniedError for protected paths or un-gated personal writes.
          """
          target_dir = self._vault / folder
          target = target_dir / f"{title}.md"

          if self._is_protected(target):
              raise PermissionDeniedError(f"Protected path: {target}")

          level = self._folder_level(folder)
          if level == "forbidden":
              raise PermissionDeniedError(f"Folder not in any write list: {folder}")

          if level == "yellow" and not _bypass_gateway:
              raise PermissionDeniedError(
                  f"Personal folder '{folder}' requires gateway — "
                  "use async write_note_via_gateway() instead"
              )

          if level == "yellow" and overwrite and target.exists() and not _bypass_gateway:
              raise PermissionDeniedError(
                  f"Overwriting existing personal note '{title}' requires RED gateway confirmation"
              )

          target_dir.mkdir(parents=True, exist_ok=True)
          body = self._build_note(title, content, tags)
          tmp = target.with_suffix(".tmp")
          tmp.write_text(body, encoding="utf-8")
          os.replace(tmp, target)

          logger.info(f"[VECTOR][obsidian] wrote {folder}/{title}.md")
          self._store_event("vault_write", f"{folder}/{title}.md")
          return target

      def append_to_note(self, title: str, content: str, folder: str, _bypass_gateway: bool = True) -> bool:
          """Append a timestamped block to an existing note (creates if missing)."""
          target_dir = self._vault / folder
          target = target_dir / f"{title}.md"

          if self._is_protected(target):
              raise PermissionDeniedError(f"Protected path: {target}")

          if not target.exists():
              return bool(self.write_note(title, content, folder, [], _bypass_gateway=_bypass_gateway))

          ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
          block = f"\n\n---\n*{ts}*\n\n{content}"
          with open(target, "a", encoding="utf-8") as f:
              f.write(block)
          logger.info(f"[VECTOR][obsidian] appended to {folder}/{title}.md")
          self._store_event("vault_append", f"{folder}/{title}.md")
          return True

      def _build_note(self, title: str, content: str, tags: list[str]) -> str:
          ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
          tag_str = ", ".join(f'"{t}"' for t in tags) if tags else ""
          frontmatter = (
              f"---\ndate: {ts}\ntags: [{tag_str}]\nsource: vector\ntype: note\n---\n\n"
          )
          return frontmatter + f"# {title}\n\n{content}\n"

      # ── Gateway-aware write (async, for personal folders) ──────────────────

      async def write_note_via_gateway(
          self,
          title: str,
          content: str,
          folder: str,
          tags: list[str],
          overwrite: bool = False,
      ) -> Path:
          """
          Routes through permission_gateway for personal folder writes.
          YELLOW for new notes, RED for overwriting existing ones.
          """
          from core.loop.permission_gateway import PermissionGateway, Action

          target = self._vault / folder / f"{title}.md"
          action_type = "overwrite_note_personal" if (overwrite and target.exists()) else "write_note_personal"
          gw = PermissionGateway()
          result = await gw.execute(Action(
              action_type=action_type,
              params={"title": title, "folder": folder, "overwrite": overwrite},
              proposed_by="obsidian_sync",
          ))
          if not result.approved:
              raise PermissionDeniedError(f"Gateway denied: {result.reason}")

          return self.write_note(title, content, folder, tags, overwrite=overwrite, _bypass_gateway=True)

      # ── Memory helper ──────────────────────────────────────────────────────

      def _get_memory(self):
          if self._memory is None:
              from core.memory.episodic import EpisodicMemory
              self._memory = EpisodicMemory()
          return self._memory

      def _store_event(self, event_type: str, note_path: str) -> None:
          try:
              self._get_memory().store(
                  event_type=event_type,
                  content=note_path,
                  tags=["obsidian", event_type],
                  source="obsidian_sync",
              )
          except Exception as e:
              logger.warning(f"[VECTOR][obsidian] episodic store failed: {e}")

      # ── LightRAG ───────────────────────────────────────────────────────────

      async def _init_rag(self):
          """Lazy-init LightRAG with Ollama backend. Gracefully degrades."""
          if self._rag is not None:
              return
          try:
              sys.path.insert(0, str(_LIGHTRAG_PATH))
              from lightrag import LightRAG, QueryParam  # noqa: F401
              from lightrag.llm.ollama import ollama_model_complete, ollama_embed
              from lightrag.utils import EmbeddingFunc
              from functools import partial

              working_dir = CONFIG.get("obsidian", {}).get(
                  "lightrag_working_dir", "./data/lightrag_vault"
              )
              Path(working_dir).mkdir(parents=True, exist_ok=True)

              ollama_host = CONFIG["ollama_host"]
              if not ollama_host.startswith("http"):
                  ollama_host = "http://" + ollama_host

              rag = LightRAG(
                  working_dir=working_dir,
                  llm_model_func=ollama_model_complete,
                  llm_model_name=CONFIG["models"]["reasoning"],
                  llm_model_kwargs={
                      "host": ollama_host,
                      "options": {"num_ctx": 8192},
                      "timeout": 120,
                  },
                  embedding_func=EmbeddingFunc(
                      embedding_dim=768,
                      max_token_size=8192,
                      func=partial(
                          ollama_embed.func,
                          embed_model=CONFIG["models"]["embed"],
                          host=ollama_host,
                      ),
                  ),
              )
              await rag.initialize_storages()
              self._rag = rag
              self._QueryParam = QueryParam
              logger.info("[VECTOR][obsidian] LightRAG initialized")
          except Exception as e:
              logger.warning(f"[VECTOR][obsidian] LightRAG init failed (degraded mode): {e}")

      async def _insert_to_rag(self, content: str) -> None:
          await self._init_rag()
          if self._rag is None:
              return
          try:
              await self._rag.ainsert(content)
          except Exception as e:
              logger.warning(f"[VECTOR][obsidian] LightRAG insert failed: {e}")

      async def query(self, text: str, mode: str = "hybrid") -> str:
          """Hybrid graph query. Returns '' gracefully if LightRAG not ready."""
          await self._init_rag()
          if self._rag is None:
              return ""
          try:
              result = await self._rag.aquery(text, param=self._QueryParam(mode=mode))
              return result or ""
          except Exception as e:
              logger.warning(f"[VECTOR][obsidian] query failed: {e}")
              return ""

      async def ingest_existing(self, folder: str | None = None) -> int:
          """
          Bulk-ingest existing vault notes into LightRAG.
          Skips already-ingested files (hash stored in semantic_memory).
          Returns count of newly ingested files.
          """
          await self._init_rag()
          if self._rag is None:
              return 0

          root = self._vault / folder if folder else self._vault
          count = 0
          mem = self._get_memory()

          for md_file in root.rglob("*.md"):
              if self._is_protected(md_file):
                  continue
              try:
                  stat = md_file.stat()
                  file_hash = hashlib.md5(
                      f"{md_file}:{stat.st_mtime}".encode()
                  ).hexdigest()[:12]
                  cache_key = f"lightrag_ingested:{file_hash}"

                  existing = mem.recall(cache_key, limit=1)
                  if existing:
                      continue

                  text = md_file.read_text(encoding="utf-8", errors="ignore")
                  if len(text.strip()) < 20:
                      continue

                  await self._insert_to_rag(text)
                  mem.remember(cache_key, "1", category="lightrag_cache")
                  count += 1
                  logger.debug(f"[VECTOR][obsidian] ingested {md_file.name}")
              except Exception as e:
                  logger.warning(f"[VECTOR][obsidian] ingest failed for {md_file}: {e}")

          logger.info(f"[VECTOR][obsidian] bulk ingest complete — {count} new files")
          return count

      async def ingest_to_rag_anything(self, file_path: str | Path) -> bool:
          """Multi-modal ingestion (PDF, image, audio) via RagAnything → same LightRAG graph."""
          await self._init_rag()
          if self._rag is None:
              return False
          try:
              sys.path.insert(0, str(_LIGHTRAG_PATH))
              from rag_anything import RAGAnything  # noqa: F401

              processor = RAGAnything(lightrag=self._rag)
              await processor.process_file(str(file_path))
              logger.info(f"[VECTOR][obsidian] RagAnything ingested {file_path}")
              return True
          except Exception as e:
              logger.warning(f"[VECTOR][obsidian] RagAnything failed: {e}")
              return False

      # ── Watchdog ───────────────────────────────────────────────────────────

      async def start_watching(self) -> None:
          """
          Watch vault for .md changes. Debounces 30s per file.
          Runs until self._watching = False. Never crashes.
          """
          import asyncio
          from watchdog.observers import Observer
          from watchdog.events import FileSystemEventHandler

          loop = asyncio.get_running_loop()
          queue: asyncio.Queue[Path] = asyncio.Queue()
          debounce_sec = CONFIG.get("obsidian", {}).get("watch_debounce_sec", 30)

          class _Handler(FileSystemEventHandler):
              def on_modified(self_, event):
                  if not event.is_directory and event.src_path.endswith(".md"):
                      loop.call_soon_threadsafe(queue.put_nowait, Path(event.src_path))

              def on_created(self_, event):
                  self_.on_modified(event)

          observer = Observer()
          observer.schedule(_Handler(), str(self._vault), recursive=True)
          observer.start()
          self._watching = True
          logger.info(f"[VECTOR][obsidian] watching vault: {self._vault}")

          seen: dict[Path, float] = {}
          import time

          try:
              while self._watching:
                  try:
                      path = await asyncio.wait_for(queue.get(), timeout=1.0)
                      seen[path] = time.monotonic()
                  except asyncio.TimeoutError:
                      pass

                  now = time.monotonic()
                  ready = [p for p, t in list(seen.items()) if now - t >= debounce_sec]
                  for p in ready:
                      del seen[p]
                      try:
                          if self._is_protected(p):
                              continue
                          text = p.read_text(encoding="utf-8", errors="ignore")
                          await self._insert_to_rag(text)
                          self._store_event("vault_change", str(p.name))
                      except Exception as e:
                          logger.warning(f"[VECTOR][obsidian] watch ingest error {p}: {e}")
          finally:
              observer.stop()
              observer.join()
              logger.info("[VECTOR][obsidian] watcher stopped")


  if __name__ == "__main__":
      import asyncio, sys
      sys.stdout.reconfigure(encoding="utf-8")
      import tempfile

      async def _smoke():
          with tempfile.TemporaryDirectory() as d:
              vault = Path(d)
              for f in ["Daily", "Reflections", "00 Notes"]:
                  (vault / f).mkdir()
              sync = ObsidianSync(vault_path=vault)

              p = sync.write_note("Smoke Test", "Hello VECTOR", "Daily", ["smoke"])
              assert p.exists(), "write_note failed"
              assert "Hello VECTOR" in p.read_text(encoding="utf-8")
              assert list(vault.glob("**/*.tmp")) == [], ".tmp file leaked"

              sync.append_to_note("Smoke Test", "appended", "Daily")
              assert "appended" in p.read_text(encoding="utf-8")

              try:
                  sync.write_note("evil", "x", "CLAUDE.md", [])
                  assert False, "should have raised"
              except PermissionDeniedError:
                  pass

              try:
                  sync.write_note("journal", "x", "00 Notes", [], _bypass_gateway=False)
                  assert False, "should have raised"
              except PermissionDeniedError:
                  pass

              personal_path = sync.write_note("journal", "x", "00 Notes", [], _bypass_gateway=True)
              assert personal_path.exists()

          print("✅ obsidian_sync.py OK")

      asyncio.run(_smoke())
  ```
- [ ] Run: `venv/Scripts/python -m pytest tests/test_obsidian_sync.py -v` → all **PASS**
- [ ] Run: `venv/Scripts/python core/memory/obsidian_sync.py` → `✅ obsidian_sync.py OK`
- [ ] Commit: `git commit -m "feat(T6): ObsidianSync write path — atomic writes, frontmatter, permission gates"`

---

### Task 5: `context_engine.py` — `get_vault_context()` + `_get_obsidian()`

- [ ] Write failing test in `tests/test_obsidian_sync.py`:
  ```python
  def test_get_vault_context_returns_string():
      from core.loop.context_engine import ContextEngine
      import asyncio
      ce = ContextEngine()
      result = asyncio.run(ce.get_vault_context("VECTOR goals"))
      assert isinstance(result, str)   # returns "" gracefully if LightRAG not ready
  ```
- [ ] Run: `venv/Scripts/python -m pytest tests/test_obsidian_sync.py::test_get_vault_context_returns_string -v` → **FAIL**
- [ ] Add to `core/loop/context_engine.py` inside the `ContextEngine` class:
  ```python
  def _get_obsidian(self):
      if self._obsidian is None:
          try:
              from core.memory.obsidian_sync import ObsidianSync
              self._obsidian = ObsidianSync()
          except Exception as e:
              logger.warning(f"[VECTOR][context_engine] ObsidianSync init failed: {e}")
      return self._obsidian

  async def get_vault_context(self, query: str) -> str:
      """LightRAG hybrid query over vault. Returns '' if not ready."""
      try:
          obs = self._get_obsidian()
          if obs is None:
              return ""
          return await obs.query(query, mode="hybrid")
      except Exception as e:
          logger.warning(f"[VECTOR][context_engine] vault context failed: {e}")
          return ""
  ```
- [ ] Add `self._obsidian = None` to `ContextEngine.__init__`
- [ ] Optionally surface vault context in `session_hydration_prompt()` — add after `recent_episodes`:
  ```python
  # vault context is async; callers that need it should await get_vault_context() separately
  # and pass result via extra_context={"vault_knowledge": vault_ctx}
  ```
- [ ] Run: `venv/Scripts/python -m pytest tests/test_obsidian_sync.py::test_get_vault_context_returns_string -v` → **PASS**
- [ ] Run: `venv/Scripts/python core/loop/context_engine.py` → no errors
- [ ] Commit: `git commit -m "feat(T6): ContextEngine.get_vault_context() — LightRAG hybrid query"`

---

### Task 6: `autonomous_loop.py` — `obsidian_loop()` coroutine

- [ ] Add `obsidian_loop()` to `AutonomousLoop`:
  ```python
  async def obsidian_loop(self) -> None:
      """Start vault watcher + bulk ingest at startup. Never crashes."""
      logger.info("[VECTOR][obsidian] loop starting")
      try:
          from core.memory.obsidian_sync import ObsidianSync
          obs = ObsidianSync()

          if CONFIG.get("obsidian", {}).get("ingest_on_startup", True):
              try:
                  count = await obs.ingest_existing()
                  logger.info(f"[VECTOR][obsidian] startup ingest: {count} files")
              except Exception as e:
                  logger.warning(f"[VECTOR][obsidian] startup ingest failed: {e}")

          await obs.start_watching()
      except Exception as e:
          logger.error(f"[VECTOR][obsidian] loop crashed: {e}")
  ```
- [ ] Add `self.obsidian_loop()` to the `asyncio.gather()` call inside `run_forever()`:
  ```python
  await asyncio.gather(
      self.observe_loop(),
      self.think_loop(),
      self.act_loop(),
      self.reflect_loop(),
      self.sync_loop(),
      self.obsidian_loop(),   # ← add this
      return_exceptions=True,
  )
  ```
- [ ] Run: `venv/Scripts/python core/loop/autonomous_loop.py` → `✅ autonomous_loop OK — N observe ticks in 2s`
- [ ] Commit: `git commit -m "feat(T6): autonomous_loop obsidian_loop — vault watcher + startup ingest"`

---

### Task 7: Full test suite + smoke test

- [ ] Run: `venv/Scripts/python -m pytest tests/ -v --tb=short` → **all pass** (≥ 52 tests)
- [ ] Run: `venv/Scripts/python core/memory/obsidian_sync.py` → `✅ obsidian_sync.py OK`
- [ ] Manual smoke — write a real note to vault:
  ```bash
  venv/Scripts/python -c "
  import asyncio
  from pathlib import Path
  from core.memory.obsidian_sync import ObsidianSync
  sync = ObsidianSync()
  p = sync.write_note(
      'VECTOR Online', 
      'T6 ObsidianSync operational. LightRAG watcher active.',
      'Daily',
      ['vector', 'milestone', 't6']
  )
  print('Written to:', p)
  "
  ```
  → File appears in `C:/Users/Arghyadeep/V.E.C.T.O.R Brain/Daily/VECTOR Online.md`
  → Note visible in Obsidian with proper frontmatter
- [ ] Commit: `git commit -m "feat(T6): ObsidianSync complete — Day 6 Obsidian gate PASS"`

---

## Day 6 Gate Check (Obsidian portion)

```
✅ VECTOR writes note to vault autonomously          → write_note() + obsidian_loop()
✅ VECTOR writes to personal folders on demand      → write_note_via_gateway()
✅ Vault changes ingested into LightRAG graph       → start_watching() + ingest_existing()
✅ Context engine surfaces vault knowledge          → get_vault_context()
✅ All 51+ tests pass                               → pytest tests/
```

**Next:** B — Memory Curator district (ConsolidationBot + PatternFinder using ObsidianSync + LightRAG)
