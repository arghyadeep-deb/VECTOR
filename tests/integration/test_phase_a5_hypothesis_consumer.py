"""Integration tests — Session A5: HypothesisEngine → SuggestionQueue → event publishing."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path


class TestSuggestionQueueCRUD(unittest.TestCase):
    """SuggestionQueue: enqueue / get_top_pending / mark_surfaced / count_pending."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        from core.brain.suggestion_queue import SuggestionQueue
        self.sq = SuggestionQueue(db_path=self._tmp.name)

    def tearDown(self):
        self.sq.close()
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_enqueue_returns_id(self):
        hid = self.sq.enqueue("Users sleep late on Fridays", confidence=0.78)
        self.assertIsInstance(hid, str)
        self.assertGreater(len(hid), 0)

    def test_enqueue_five_then_get_three(self):
        texts = [f"Hypothesis {i}" for i in range(5)]
        for i, t in enumerate(texts):
            self.sq.enqueue(t, confidence=0.5 + i * 0.05)
        pending = self.sq.get_top_pending(limit=3)
        self.assertEqual(len(pending), 3)

    def test_top_pending_sorted_by_confidence_desc(self):
        self.sq.enqueue("Low conf", confidence=0.4)
        self.sq.enqueue("High conf", confidence=0.9)
        self.sq.enqueue("Mid conf", confidence=0.6)
        pending = self.sq.get_top_pending(limit=3)
        confs = [p["confidence"] for p in pending]
        self.assertEqual(confs, sorted(confs, reverse=True))

    def test_mark_surfaced_removes_from_pending(self):
        hid = self.sq.enqueue("Test hypothesis", confidence=0.8)
        self.assertEqual(self.sq.count_pending(), 1)
        self.sq.mark_surfaced(hid)
        self.assertEqual(self.sq.count_pending(), 0)

    def test_mark_surfaced_sets_status(self):
        hid = self.sq.enqueue("Another test", confidence=0.7)
        self.sq.mark_surfaced(hid)
        all_rows = self.sq.get_all(limit=10)
        row = next((r for r in all_rows if r["id"] == hid), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "surfaced")
        self.assertIsNotNone(row["surfaced_at"])

    def test_no_pending_returns_empty(self):
        pending = self.sq.get_top_pending(limit=3)
        self.assertEqual(pending, [])

    def test_get_all_returns_all_statuses(self):
        self.sq.enqueue("Pending one", confidence=0.7)
        hid2 = self.sq.enqueue("To be surfaced", confidence=0.85)
        self.sq.mark_surfaced(hid2)
        all_rows = self.sq.get_all(limit=10)
        statuses = {r["status"] for r in all_rows}
        self.assertIn("pending", statuses)
        self.assertIn("surfaced", statuses)


class TestHypothesisEngineEnqueues(unittest.TestCase):
    """HypothesisEngine.generate_hypotheses() enqueues to SuggestionQueue."""

    def test_hypothesis_has_confidence_field(self):
        """generate_hypotheses result must include confidence key."""
        import asyncio
        from core.brain.hypothesis_engine import HypothesisEngine
        he = HypothesisEngine()
        # generate_hypotheses calls Ollama which may not be running — check that at least
        # when a hypothesis IS created it has the confidence field
        # Test via direct injection into _hypotheses
        he._hypotheses = []
        # Simulate what generate_hypotheses produces (Ollama absent → falls into except)
        # We just verify the field is wired in the success path by checking the code
        import inspect
        src = inspect.getsource(he.generate_hypotheses)
        self.assertIn("confidence", src, "generate_hypotheses must set 'confidence' key on hypothesis")
        self.assertIn("SuggestionQueue", src, "generate_hypotheses must enqueue to SuggestionQueue")

    def test_suggestion_queue_enqueue_via_direct_call(self):
        """Enqueue a hypothesis directly and verify it appears pending."""
        import tempfile
        from core.brain.suggestion_queue import SuggestionQueue
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            sq = SuggestionQueue(db_path=db)
            sq.enqueue("Morning productivity peak at 9am", confidence=0.82)
            sq.enqueue("Late commits correlate with bugs", confidence=0.71)
            sq.enqueue("Screen brightness affects fatigue", confidence=0.65)
            sq.enqueue("Pomodoro sessions improve focus", confidence=0.77)
            sq.enqueue("Deep work blocks > 90min not beneficial", confidence=0.68)
            self.assertEqual(sq.count_pending(), 5)
            top3 = sq.get_top_pending(limit=3)
            self.assertEqual(len(top3), 3)
            # Highest confidence first
            self.assertAlmostEqual(top3[0]["confidence"], 0.82)
            sq.close()
        finally:
            Path(db).unlink(missing_ok=True)


class TestEventTypeSurfaced(unittest.TestCase):
    """EventType.HYPOTHESIS_SURFACED exists and has the expected value."""

    def test_hypothesis_surfaced_in_event_type(self):
        from core.event_bus.types import EventType
        names = [e.name for e in EventType]
        self.assertIn("HYPOTHESIS_SURFACED", names)

    def test_hypothesis_surfaced_value(self):
        from core.event_bus.types import EventType
        self.assertEqual(EventType.HYPOTHESIS_SURFACED.value, "hypothesis_surfaced")


class TestNotificationsRouter(unittest.TestCase):
    """notifications.py router exports correct shape."""

    def test_router_importable(self):
        from core.api.routers.notifications import router
        self.assertIsNotNone(router)

    def test_router_has_hypotheses_route(self):
        from core.api.routers.notifications import router
        paths = [r.path for r in router.routes]
        self.assertIn("/notifications/hypotheses", paths)

    def test_router_has_ws_route(self):
        from core.api.routers.notifications import router
        paths = [r.path for r in router.routes]
        self.assertIn("/notifications/ws", paths)


class TestReflectTickHypothesisDrain(unittest.TestCase):
    """_reflect_tick wires SuggestionQueue drain + HYPOTHESIS_SURFACED publish."""

    def test_reflect_tick_imports_suggestion_queue(self):
        """autonomous_loop._reflect_tick source must reference SuggestionQueue."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop
        src = inspect.getsource(AutonomousLoop._reflect_tick)
        self.assertIn("SuggestionQueue", src)
        self.assertIn("HYPOTHESIS_SURFACED", src)

    def test_daily_reviewer_includes_proactive_insights(self):
        """daily_reviewer.review source must reference SuggestionQueue and 'I noticed'."""
        import inspect
        from districts.reflection.daily_reviewer import DailyReviewer
        src = inspect.getsource(DailyReviewer.review)
        self.assertIn("SuggestionQueue", src)
        self.assertIn("I noticed", src)


class TestHypothesisLoopActuallyExecutes:
    """MUST-FIX blocker #1 regression tests (see
    VECTOR_TECHNICAL_KNOWLEDGE/51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md §16.A
    and VECTOR_TECHNICAL_KNOWLEDGE/52_AUTONOMY_BLOCKER_REMEDIATION.md).

    autonomous_loop.py's hypothesis_loop() called the async
    HypothesisEngine.generate_hypotheses() WITHOUT `await` — the coroutine
    object was truthy but never run, so the underlying LLM call never
    fired and every cycle silently took the "low confidence, suppressed"
    branch. TestHypothesisEngineEnqueues.test_hypothesis_has_confidence_field
    above only proves this via inspect.getsource() string matching, which
    cannot catch a missing `await` (the string "confidence" is present in
    the source either way) — that's exactly how this bug went undetected.

    These tests instead call the real coroutine body and assert the
    generation method was actually AWAITED (not just referenced), using a
    pytest-asyncio native async test (this repo runs asyncio_mode=auto —
    see pytest.ini/pyproject.toml — so a bare `async def test_...` is
    collected and run directly, same pattern as
    tests/unit/test_loop_stall_fixes.py).
    """

    async def test_generate_hypotheses_is_actually_awaited(self, monkeypatch):
        """A. hypothesis_loop() must actually execute (await) the async
        generate_hypotheses() coroutine, not merely construct it.

        Verified by making generate_hypotheses() itself observably run its
        body (increments a counter BEFORE returning) — if the caller only
        constructs the coroutine without awaiting it, the coroutine body
        never executes and the counter stays at 0. This is the exact
        failure mode the missing `await` produced."""
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        loop = AutonomousLoop()
        loop._running = True

        call_count = {"n": 0}

        class FakeEngine:
            async def generate_hypotheses(self, observation):
                # This line only runs if the coroutine is actually awaited.
                call_count["n"] += 1
                return {"id": "1", "text": "test hypothesis", "confidence": 0.9}

        mock_engine = FakeEngine()
        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: mock_engine)

        mock_context = MagicMock()
        mock_context.get_world_state.return_value = {"time_of_day": "morning"}
        monkeypatch.setattr(loop, "_get_context", lambda: mock_context)

        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        # Drive hypothesis_loop's body directly rather than waiting out its
        # real 4h `asyncio.sleep` — same technique as
        # TestReflectTickTimeoutCoverage in test_loop_stall_fixes.py, which
        # calls the tick logic directly instead of the full while-loop
        # wrapper. hypothesis_loop's sleep is at the top of its try block,
        # so patch asyncio.sleep to return immediately and let the loop run
        # exactly one real iteration before we stop it.
        real_sleep = asyncio.sleep
        iterations = {"n": 0}

        async def fast_sleep(_seconds):
            iterations["n"] += 1
            if iterations["n"] > 1:
                loop._running = False
            await real_sleep(0)  # yield control, don't actually wait

        monkeypatch.setattr(
            "core.loop.autonomous_loop.asyncio.sleep", fast_sleep
        )

        await loop.hypothesis_loop()

        assert call_count["n"] == 1, (
            "generate_hypotheses() coroutine body never executed — it was "
            "constructed but not awaited (the exact bug this test guards "
            "against)"
        )
        # The high-confidence (0.9 >= 0.85) result must have been stored.
        assert mock_memory.store.called
        stored_kwargs = mock_memory.store.call_args.kwargs
        assert stored_kwargs["event_type"] == "hypothesis"
        # Key-contract fix (see VECTOR_TECHNICAL_KNOWLEDGE/55_HYPOTHESIS_
        # PIPELINE_REMEDIATION.md): hypothesis_loop() previously read
        # h.get("hypothesis", str(h)) at autonomous_loop.py:2874, but
        # generate_hypotheses() has always returned its text under the key
        # "text" (hypothesis_engine.py) — so the old code always fell
        # through to str(h), storing the whole dict's repr instead of the
        # actual hypothesis text. hypothesis_loop() now reads h.get("text",
        # ...), so the stored content must be the plain hypothesis text.
        assert stored_kwargs["content"] == "test hypothesis"
        assert stored_kwargs["content"] != str(
            {"id": "1", "text": "test hypothesis", "confidence": 0.9}
        )

    async def test_hypothesis_loop_source_awaits_generate_hypotheses(self):
        """Static guard (belt-and-suspenders alongside the dynamic test
        above): fail loudly if a future edit removes the `await` again.
        This alone would NOT have caught the original bug (the source
        contained "generate_hypotheses(" either way) — it only guards
        against regressing the fix now that it's dynamically verified."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop

        src = inspect.getsource(AutonomousLoop.hypothesis_loop)
        assert "await engine.generate_hypotheses(observation)" in src, (
            "hypothesis_loop() must await generate_hypotheses() — a bare "
            "'engine.generate_hypotheses(observation)' call constructs the "
            "coroutine without running it. (Argument is 'observation', not "
            "the raw 'context' dict, since 56_HYPOTHESIS_OBSERVATION_"
            "CONTRACT.md's fix — get_world_state()'s dict is converted to "
            "a string before this call.)"
        )

    async def test_low_confidence_hypothesis_is_suppressed_not_stored(self, monkeypatch):
        """Existing suppression logic (confidence < 0.85) must be
        preserved unchanged by the await fix."""
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        loop = AutonomousLoop()
        loop._running = True

        class FakeEngine:
            async def generate_hypotheses(self, observation):
                return {"id": "1", "text": "low confidence guess", "confidence": 0.5}

        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: FakeEngine())
        mock_context = MagicMock()
        mock_context.get_world_state.return_value = {}
        monkeypatch.setattr(loop, "_get_context", lambda: mock_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        real_sleep = asyncio.sleep
        iterations = {"n": 0}

        async def fast_sleep(_seconds):
            iterations["n"] += 1
            if iterations["n"] > 1:
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        await loop.hypothesis_loop()

        assert not mock_memory.store.called, (
            "low-confidence hypothesis (0.5 < 0.85) must be suppressed, "
            "not written to memory — this is pre-existing behavior, "
            "unchanged by the await fix"
        )

    async def test_generation_exception_does_not_kill_loop(self, monkeypatch):
        """B. An exception raised inside (now-awaited) generate_hypotheses()
        must be caught by hypothesis_loop()'s existing except block and
        the loop must continue (RULE 2 — never dies), not propagate and
        kill the supervised coroutine.

        Before the fix, an exception inside generate_hypotheses() could
        NEVER reach this except block at all — the coroutine was never
        awaited, so it never ran, so it could never raise. This test would
        have been vacuously "passing" (no exception, no crash) even with
        the bug present, which is exactly why the failure needed the
        dynamic call-count proof above rather than only this test."""
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        loop = AutonomousLoop()
        loop._running = True

        class FailingEngine:
            async def generate_hypotheses(self, observation):
                raise RuntimeError("simulated LLM/provider failure")

        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: FailingEngine())
        mock_context = MagicMock()
        mock_context.get_world_state.return_value = {}
        monkeypatch.setattr(loop, "_get_context", lambda: mock_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        # hypothesis_loop's except-block sleeps 300s on error; that sleep
        # also goes through asyncio.sleep, so keep the same fast-forward
        # shim and stop the outer while-loop after the error-recovery
        # sleep fires once.
        real_sleep = asyncio.sleep
        sleep_calls = []

        async def fast_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:  # 1: the 4h tick sleep, 2: the 300s error backoff
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        # Must return normally — an unhandled exception escaping
        # hypothesis_loop() would be the failure mode under test.
        await loop.hypothesis_loop()

        assert sleep_calls[0] == 4 * 3600  # the normal 4h cadence, untouched
        assert sleep_calls[1] == 300  # the existing error-backoff sleep fired
        assert not mock_memory.store.called


class TestHypothesisPipelineTextAndConfidenceContract:
    """Regression tests for two collateral defects discovered while fixing
    MUST-FIX blocker #1's missing `await` (see
    VECTOR_TECHNICAL_KNOWLEDGE/55_HYPOTHESIS_PIPELINE_REMEDIATION.md):

    1. hypothesis_loop() read h.get("hypothesis", ...) but
       generate_hypotheses() has always returned its text under "text" —
       fixed at autonomous_loop.py:2874 (now h.get("text", ...)).
    2. generate_hypotheses() hardcoded confidence=0.7, permanently below
       hypothesis_loop()'s 0.85 storage gate — fixed by parsing a genuine
       LLM self-rated "CONFIDENCE: <n>" marker the prompt now requests,
       following the same self-rated-confidence convention already used by
       core/brain/anticipation.py (`float(item.get("confidence", 0.6))`
       from a JSON field) and core/brain/council.py
       (`raw.get("confidence", 0.75)`), adapted to this engine's free-text
       (non-JSON) response format.

    Unlike TestHypothesisLoopActuallyExecutes above (which stands in a
    FakeEngine to isolate hypothesis_loop()'s own behavior), these tests
    exercise the REAL HypothesisEngine class — only the network call inside
    HypothesisEngine._call is mocked — so they actually prove the
    producer/consumer contract end to end, not just the consumer's
    handling of an already-correct dict.
    """

    async def test_confidence_is_llm_derived_not_hardcoded(self, monkeypatch):
        """D, E. generate_hypotheses() must parse a real, varying
        confidence from the LLM response instead of returning a hardcoded
        constant (previously always 0.7 regardless of content — confirmed
        via git history to have been a static literal since the file's
        creation, never computed from anything)."""
        from core.brain.hypothesis_engine import HypothesisEngine

        engine = HypothesisEngine()

        async def fake_call_high(*_a, **_kw):
            return "The owner is more productive in the morning.\n\nCONFIDENCE: 0.92"

        # NOTE: observation is passed as a plain string here deliberately —
        # generate_hypotheses()'s logging line does observation[:50], which
        # raises TypeError on a dict (a separate, pre-existing, out-of-scope
        # defect: hypothesis_loop() actually calls generate_hypotheses(dict)
        # since get_world_state() returns a dict, not a str; see
        # VECTOR_TECHNICAL_KNOWLEDGE/55_HYPOTHESIS_PIPELINE_REMEDIATION.md
        # "Remaining limitations"). Using a string here isolates this test
        # to the confidence contract only.
        monkeypatch.setattr(engine, "_call", fake_call_high)
        high = await engine.generate_hypotheses("owner morning activity pattern")
        assert high["confidence"] == 0.92

        async def fake_call_low(*_a, **_kw):
            return "The owner might prefer tea.\n\nCONFIDENCE: 0.31"

        monkeypatch.setattr(engine, "_call", fake_call_low)
        low = await engine.generate_hypotheses("owner morning activity pattern")
        assert low["confidence"] == 0.31

        # The two calls must differ — proves confidence tracks the LLM's
        # own response rather than a fixed constant.
        assert high["confidence"] != low["confidence"]
        assert high["confidence"] != 0.7
        assert low["confidence"] != 0.7

    async def test_confidence_marker_stripped_from_stored_text(self, monkeypatch):
        """A. The 'CONFIDENCE: <n>' marker the prompt requests must not
        leak into the human-facing hypothesis text."""
        from core.brain.hypothesis_engine import HypothesisEngine

        engine = HypothesisEngine()

        async def fake_call(*_a, **_kw):
            return "Owner works better before noon.\n\nCONFIDENCE: 0.9"

        monkeypatch.setattr(engine, "_call", fake_call)
        result = await engine.generate_hypotheses("owner morning activity pattern")
        assert result["text"] == "Owner works better before noon."
        assert "CONFIDENCE" not in result["text"]

    async def test_confidence_parse_fallback_when_marker_missing(self, monkeypatch):
        """If the LLM omits the confidence marker, generate_hypotheses()
        must fall back to a conservative default (below the 0.85 storage
        gate) rather than crashing or silently guessing high. This is a
        documented, deliberately conservative fallback — not a claim that
        0.5 is the "correct" confidence for an unparseable response, just
        that suppression is the safe default when confidence is unknown."""
        from core.brain.hypothesis_engine import HypothesisEngine

        engine = HypothesisEngine()

        async def fake_call(*_a, **_kw):
            return "Owner prefers dark mode at night."

        monkeypatch.setattr(engine, "_call", fake_call)
        result = await engine.generate_hypotheses("owner night activity pattern")
        assert result["confidence"] == 0.5
        assert result["confidence"] < 0.85
        assert result["text"] == "Owner prefers dark mode at night."

    async def test_real_engine_qualifying_hypothesis_reaches_stored_memory_as_text(
        self, monkeypatch
    ):
        """C, D, plus Part 4 items 2/3/5/8 end-to-end: real HypothesisEngine
        → real hypothesis_loop() → stored memory contains the actual
        hypothesis text (not str(dict)), with the confidence value the LLM
        actually emitted (not the old hardcoded 0.7). Existing 4h cadence
        must be unchanged. This is the behavioral regression test required
        by Part 2 — it executes the real relevant code path end to end."""
        from core.brain.hypothesis_engine import HypothesisEngine
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        engine = HypothesisEngine()

        async def fake_call(*_a, **_kw):
            return "The owner works better before noon.\n\nCONFIDENCE: 0.93"

        monkeypatch.setattr(engine, "_call", fake_call)

        loop = AutonomousLoop()
        loop._running = True
        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: engine)
        mock_context = MagicMock()
        # String, not dict — see the NOTE in test_confidence_is_llm_derived_
        # not_hardcoded above for why (a separate, out-of-scope dict/str
        # mismatch bug in the real observation[:50] logging call).
        mock_context.get_world_state.return_value = "owner morning activity pattern"
        monkeypatch.setattr(loop, "_get_context", lambda: mock_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        real_sleep = asyncio.sleep
        sleep_calls = []

        async def fast_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) > 1:
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        await loop.hypothesis_loop()

        assert sleep_calls[0] == 4 * 3600  # cadence unchanged
        assert mock_memory.store.called
        stored_kwargs = mock_memory.store.call_args.kwargs
        assert stored_kwargs["content"] == "The owner works better before noon."
        assert "CONFIDENCE" not in stored_kwargs["content"]
        assert not stored_kwargs["content"].startswith("{")
        assert stored_kwargs["context"]["confidence"] == 0.93

    async def test_real_engine_below_threshold_confidence_suppressed_end_to_end(
        self, monkeypatch
    ):
        """F, part 4 item 6 end-to-end: a genuinely low-confidence
        real-engine hypothesis must still be suppressed by the unchanged
        0.85 gate — the fix makes confidence vary with content, but does
        not weaken the storage threshold."""
        from core.brain.hypothesis_engine import HypothesisEngine
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        engine = HypothesisEngine()

        async def fake_call(*_a, **_kw):
            return "Owner might like blue better.\n\nCONFIDENCE: 0.40"

        monkeypatch.setattr(engine, "_call", fake_call)

        loop = AutonomousLoop()
        loop._running = True
        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: engine)
        mock_context = MagicMock()
        mock_context.get_world_state.return_value = "weak observation, unclear pattern"
        monkeypatch.setattr(loop, "_get_context", lambda: mock_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        real_sleep = asyncio.sleep
        iterations = {"n": 0}

        async def fast_sleep(_seconds):
            iterations["n"] += 1
            if iterations["n"] > 1:
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        await loop.hypothesis_loop()

        assert not mock_memory.store.called

    async def test_real_engine_llm_failure_does_not_kill_loop(self, monkeypatch):
        """Part 4 item 7 via the REAL engine's own internal error handling:
        generate_hypotheses() catches _call() failures itself and returns
        {"error": ...} rather than raising — hypothesis_loop() must treat
        that as a non-crash (no "confidence" key on an error dict → treated
        as 0.0 → suppressed, loop continues). This is a different but
        equally valid resilience path from
        test_generation_exception_does_not_kill_loop above (which exercises
        hypothesis_loop()'s own except block when the engine itself raises
        instead of catching)."""
        from core.brain.hypothesis_engine import HypothesisEngine
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        engine = HypothesisEngine()

        async def failing_call(*_a, **_kw):
            raise RuntimeError("simulated provider outage")

        monkeypatch.setattr(engine, "_call", failing_call)

        loop = AutonomousLoop()
        loop._running = True
        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: engine)
        mock_context = MagicMock()
        mock_context.get_world_state.return_value = "owner evening activity pattern"
        monkeypatch.setattr(loop, "_get_context", lambda: mock_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        real_sleep = asyncio.sleep
        iterations = {"n": 0}

        async def fast_sleep(_seconds):
            iterations["n"] += 1
            if iterations["n"] > 1:
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        # Must return normally — no unhandled exception escapes.
        await loop.hypothesis_loop()
        assert not mock_memory.store.called


class TestHypothesisObservationContract:
    """Regression tests for the observation-contract defect documented in
    VECTOR_TECHNICAL_KNOWLEDGE/56_HYPOTHESIS_OBSERVATION_CONTRACT.md:

    ContextEngine.get_world_state() always returns a dict (its declared
    -> dict type, and every other of its 6+ callers — decision_engine.py,
    planner.py, chief_of_staff.py, subconscious_loop.py, etc. — treat it as
    one via dict access). HypothesisEngine.generate_hypotheses(observation:
    str) is consistently string-typed instead (its own signature, its
    prompt template, its observation[:50] logging slice, and every OTHER
    caller of generate_hypotheses() already pass a plain string). But
    hypothesis_loop() passed the raw dict straight through, so
    generate_hypotheses() hit `observation[:50]` (a dict, not sliceable by
    an int) on EVERY invocation, was caught by generate_hypotheses()'s own
    broad except, and returned {"error": ...} — meaning hypothesis_loop()
    likely never reached a real LLM call in production at all, regardless
    of the Blocker 1 await fix or the key/confidence fixes in
    55_HYPOTHESIS_PIPELINE_REMEDIATION.md.

    Classification: B — CONTRACT MISMATCH, CALLER BUG. Fixed at the
    boundary closest to the mismatch (hypothesis_loop() itself), reusing
    the str(world_state)[:500] convention districts/chief_of_staff/
    subconscious_loop.py already uses to turn get_world_state()'s dict into
    LLM-prompt text — not a new serialization format.

    These tests use the REAL ContextEngine AND the REAL HypothesisEngine —
    only the network call inside HypothesisEngine._call is mocked — per
    Part 4's requirement not to use a FakeEngine for the core boundary
    test.
    """

    async def test_real_world_state_reaches_real_engine_as_string_and_is_stored(
        self, monkeypatch
    ):
        """Items 1-6, 10. The actual dict ContextEngine.get_world_state()
        returns must reach HypothesisEngine._call() as a string (proving
        observation[:50] never raises), and the resulting hypothesis must
        flow through confidence extraction and out to EpisodicMemory
        storage as plain text, with the 4h cadence unchanged."""
        from core.loop.context_engine import ContextEngine
        from core.brain.hypothesis_engine import HypothesisEngine
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        real_context = ContextEngine()
        engine = HypothesisEngine()

        captured = {}

        async def fake_call(user_prompt, temperature=0.5, max_tokens=800):
            # If observation were still the raw dict, generate_hypotheses()
            # would have raised inside its own observation[:50] logging
            # slice BEFORE ever reaching _call() — so simply landing here
            # at all is part of the proof. Capture the prompt for content
            # assertions below.
            captured["prompt"] = user_prompt
            return "The owner's recent activity looks routine.\n\nCONFIDENCE: 0.91"

        monkeypatch.setattr(engine, "_call", fake_call)

        loop = AutonomousLoop()
        loop._running = True
        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: engine)
        monkeypatch.setattr(loop, "_get_context", lambda: real_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        real_sleep = asyncio.sleep
        sleep_calls = []

        async def fast_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) > 1:
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        await loop.hypothesis_loop()

        assert sleep_calls[0] == 4 * 3600  # cadence unchanged

        # _call() was reached at all — proves generate_hypotheses() did not
        # die inside observation[:50] on a raw dict.
        assert "prompt" in captured
        assert "Given this observation, generate" in captured["prompt"]
        # The real world-state dict's content must actually be present in
        # the prompt text (proves it's a real conversion of the real
        # get_world_state() dict, not an empty string or a placeholder).
        assert "time_of_day" in captured["prompt"] or "timestamp" in captured["prompt"]

        assert mock_memory.store.called
        stored_kwargs = mock_memory.store.call_args.kwargs
        assert stored_kwargs["content"] == "The owner's recent activity looks routine."
        assert "CONFIDENCE" not in stored_kwargs["content"]
        assert stored_kwargs["context"]["confidence"] == 0.91

    async def test_real_world_state_below_threshold_confidence_still_suppressed(
        self, monkeypatch
    ):
        """Item 8, with the real observation-conversion boundary in place:
        a genuinely low real-engine confidence is still suppressed by the
        unchanged 0.85 gate."""
        from core.loop.context_engine import ContextEngine
        from core.brain.hypothesis_engine import HypothesisEngine
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        real_context = ContextEngine()
        engine = HypothesisEngine()

        async def fake_call(*_a, **_kw):
            return "Owner might prefer blue.\n\nCONFIDENCE: 0.35"

        monkeypatch.setattr(engine, "_call", fake_call)

        loop = AutonomousLoop()
        loop._running = True
        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: engine)
        monkeypatch.setattr(loop, "_get_context", lambda: real_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        real_sleep = asyncio.sleep
        iterations = {"n": 0}

        async def fast_sleep(_seconds):
            iterations["n"] += 1
            if iterations["n"] > 1:
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        await loop.hypothesis_loop()

        assert not mock_memory.store.called

    async def test_real_world_state_llm_failure_remains_contained(self, monkeypatch):
        """Item 9, with the real observation-conversion boundary in place:
        a provider failure inside the real generate_hypotheses() (called
        with a real, converted observation) must not kill the loop."""
        from core.loop.context_engine import ContextEngine
        from core.brain.hypothesis_engine import HypothesisEngine
        from core.loop.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        real_context = ContextEngine()
        engine = HypothesisEngine()

        async def failing_call(*_a, **_kw):
            raise RuntimeError("simulated provider outage")

        monkeypatch.setattr(engine, "_call", failing_call)

        loop = AutonomousLoop()
        loop._running = True
        monkeypatch.setattr(loop, "_get_hypothesis_engine", lambda: engine)
        monkeypatch.setattr(loop, "_get_context", lambda: real_context)
        mock_memory = MagicMock()
        monkeypatch.setattr(loop, "_get_memory", lambda: mock_memory)

        real_sleep = asyncio.sleep
        iterations = {"n": 0}

        async def fast_sleep(_seconds):
            iterations["n"] += 1
            if iterations["n"] > 1:
                loop._running = False
            await real_sleep(0)

        monkeypatch.setattr("core.loop.autonomous_loop.asyncio.sleep", fast_sleep)

        # Must return normally.
        await loop.hypothesis_loop()
        assert not mock_memory.store.called

    def test_get_world_state_returns_dict_confirming_the_contract(self):
        """Direct evidence for Part 1, item 1-3: get_world_state()'s
        declared and actual return type is dict, not str — this is the
        premise the observation-conversion fix depends on."""
        from core.loop.context_engine import ContextEngine

        state = ContextEngine().get_world_state()
        assert isinstance(state, dict)
        # A dict this shape is exactly what would have broken
        # observation[:50] pre-fix — dict.__getitem__(slice(...)) raises
        # KeyError (dicts have no slicing support; the slice object is just
        # looked up as an ordinary, absent key).
        with_slice_error = False
        try:
            state[:50]
        except (KeyError, TypeError):
            with_slice_error = True
        assert with_slice_error, (
            "if this dict were somehow sliceable, the original defect "
            "this fix addresses would not have existed"
        )


if __name__ == "__main__":
    unittest.main()
