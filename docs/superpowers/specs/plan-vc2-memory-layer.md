# VectorCode VC-2: Memory Layer

**Goal:** Build the FAISS-backed vector index, SONA pattern cache, and auto-memory bridge that give VectorCode self-learning capabilities.
**Architecture:** FAISSIndex uses faiss.IndexHNSWFlat with nomic-embed-text embeddings (768-dim via Ollama). PatternStore wraps FAISSIndex to store/retrieve successful task patterns, writing rewards to reasoning_chains. AutoMemoryBridge syncs bidirectionally between the file-based Claude memory system and FAISSIndex every 5 minutes as a background TaskQueue task.
**Files:**
- Create: `agents/districts/coding/vectorcode/memory/__init__.py`
- Create: `agents/districts/coding/vectorcode/memory/faiss_index.py`
- Create: `agents/districts/coding/vectorcode/memory/pattern_store.py`
- Create: `agents/districts/coding/vectorcode/memory/auto_bridge.py`
- Create: `tests/test_vectorcode_vc2.py`

---

### Task 1: FAISSIndex — HNSW vector index with SQLite metadata

- [ ] Write failing test
  ```python
  from agents.districts.coding.vectorcode.memory.faiss_index import FAISSIndex
  def test_faiss_add_and_search(tmp_path):
      idx = FAISSIndex(index_path=str(tmp_path / "test.index"), dim=768)
      idx.add("doc1", [0.1] * 768, {"text": "write a login function"})
      idx.add("doc2", [0.9] * 768, {"text": "deploy to production"})
      results = idx.search([0.1] * 768, k=1)
      assert len(results) == 1
      assert results[0]["id"] == "doc1"
  def test_faiss_persist_reload(tmp_path):
      idx = FAISSIndex(index_path=str(tmp_path / "persist.index"), dim=768)
      idx.add("x1", [0.5] * 768, {"text": "test"})
      idx.save()
      idx2 = FAISSIndex(index_path=str(tmp_path / "persist.index"), dim=768)
      idx2.load()
      results = idx2.search([0.5] * 768, k=1)
      assert results[0]["id"] == "x1"
  def test_faiss_similarity_threshold(tmp_path):
      idx = FAISSIndex(index_path=str(tmp_path / "t.index"), dim=768)
      idx.add("close", [0.1] * 768, {"text": "close"})
      idx.add("far", [0.9] * 768, {"text": "far"})
      results = idx.search([0.1] * 768, k=2, min_score=0.9)
      ids = [r["id"] for r in results]
      assert "close" in ids
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc2.py -k "faiss" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/memory/faiss_index.py`
- [ ] Run: `pytest tests/test_vectorcode_vc2.py -k "faiss" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc2): FAISSIndex HNSW vector index"`

---

### Task 2: PatternStore — SONA port (task patterns → reasoning_chains)

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from agents.districts.coding.vectorcode.memory.pattern_store import PatternStore
  def test_pattern_store_save_and_recall(tmp_path):
      with patch("agents.districts.coding.vectorcode.memory.pattern_store.FAISSIndex") as MockFAISS:
          mock_idx = MagicMock()
          mock_idx.search.return_value = [{"id": "p1", "score": 0.95, "meta": {"plan": "step1,step2", "outcome": "success"}}]
          MockFAISS.return_value = mock_idx
          ps = PatternStore(index_path=str(tmp_path / "patterns"))
          ps.save_pattern(task="write login", plan=["step1", "step2"], outcome="success", reward=0.9)
          result = ps.recall(task="write login function")
          assert result is not None
          assert result["reward"] >= 0.0
  def test_pattern_store_skip_below_threshold(tmp_path):
      with patch("agents.districts.coding.vectorcode.memory.pattern_store.FAISSIndex") as MockFAISS:
          mock_idx = MagicMock()
          mock_idx.search.return_value = [{"id": "p1", "score": 0.3, "meta": {"plan": "x"}}]
          MockFAISS.return_value = mock_idx
          ps = PatternStore(index_path=str(tmp_path / "patterns"))
          result = ps.recall(task="completely unrelated task")
          assert result is None
  def test_pattern_store_reward_updates_policy(tmp_path):
      with patch("agents.districts.coding.vectorcode.memory.pattern_store.FAISSIndex"):
          with patch("agents.districts.coding.vectorcode.memory.pattern_store.EpisodicMemory") as MockMem:
              mock_mem = MagicMock()
              MockMem.return_value = mock_mem
              ps = PatternStore(index_path=str(tmp_path / "patterns"))
              ps.save_pattern("test task", ["step1"], "success", reward=0.85)
              mock_mem.store_chain.assert_called_once()
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc2.py -k "pattern" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/memory/pattern_store.py`
- [ ] Run: `pytest tests/test_vectorcode_vc2.py -k "pattern" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc2): PatternStore SONA cache → reasoning_chains"`

---

### Task 3: AutoMemoryBridge — bidirectional memory sync

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from agents.districts.coding.vectorcode.memory.auto_bridge import AutoMemoryBridge
  def test_bridge_sync_reads_episodic(tmp_path):
      with patch("agents.districts.coding.vectorcode.memory.auto_bridge.EpisodicMemory") as MockMem:
          with patch("agents.districts.coding.vectorcode.memory.auto_bridge.FAISSIndex") as MockFAISS:
              mock_mem = MagicMock()
              mock_mem.recall.return_value = [{"content": "learned pattern", "tags": ["code"]}]
              MockMem.return_value = mock_mem
              MockFAISS.return_value = MagicMock()
              bridge = AutoMemoryBridge(index_path=str(tmp_path / "bridge"))
              bridge.sync_episodic_to_faiss()
              MockFAISS.return_value.add.assert_called()
  def test_bridge_sync_interval():
      bridge = AutoMemoryBridge.__new__(AutoMemoryBridge)
      assert hasattr(AutoMemoryBridge, "SYNC_INTERVAL_SEC")
      assert AutoMemoryBridge.SYNC_INTERVAL_SEC == 300
  def test_bridge_insight_categories():
      expected = {"patterns", "debugging", "architecture", "performance", "security", "preferences"}
      assert set(AutoMemoryBridge.INSIGHT_CATEGORIES) == expected
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc2.py -k "bridge" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/memory/auto_bridge.py`
- [ ] Run: `pytest tests/test_vectorcode_vc2.py -k "bridge" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc2): AutoMemoryBridge bidirectional memory sync"`

---

### Task 4: Full VC-2 integration smoke

- [ ] Run: `pytest tests/test_vectorcode_vc2.py -v` → all pass
- [ ] Commit: `git commit -m "feat(vc2): memory layer complete — FAISS/PatternStore/AutoBridge"`
