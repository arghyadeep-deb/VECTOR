"""RealtimeConversation — full-duplex voice orchestrator (design Phases 2-5).

Implements docs/REALTIME_CONVERSATION_DESIGN.md on top of existing modules:
  ConversationManager (FSM)  · VoiceActivityDetector (endpointing + barge-in)
  WhisperSTT/FasterWhisperSTT (partial + final transcripts)
  VoiceTTS/Kokoro (per-sentence synthesis) · rules_engine (instant bypass)
  Governor (action handoff, RULE 3 intact)  · nudge_engine (proactive speech)
  presence.allow_proactive (DND / reactive-mode gate)

Transport-agnostic: the WS router passes a `send_json` coroutine; everything
else is callbacks. One instance per connected duplex client.

Turn lifecycle (§6 of the design):
  LISTENING -> USER_SPEAKING (VAD speech) -> partial decodes every ~600ms
  -> endpoint at `endpoint_silence_ms` of silence -> final transcript
  -> PROCESSING (rules bypass | intent classify) ->
       chat:   streaming LLM -> sentence TTS  (VECTOR_SPEAKING)
       action: spoken ack -> governor.dispatch() async -> completion spoken
  -> LISTENING.  Barge-in (§7): speech while VECTOR_SPEAKING cancels the
  speak task, sends {"type":"stop_audio"}, returns to LISTENING.
"""

from __future__ import annotations

__all__ = ["RealtimeConversation"]

import asyncio
import contextlib
import base64
import io
import json
import re
import sys
import time
from collections.abc import AsyncIterator
from concurrent.futures import Future
from itertools import count, cycle

import numpy as np
from loguru import logger

from core.config import CONFIG


# ── sentence streaming helpers (shared with the legacy push-to-talk path) ────

_SENTENCE_ENDS = (".", "!", "?", "\n")
_REALTIME_TTS = None
_REALTIME_TTS_FUTURE: Future | None = None
_OLLAMA_STREAM_CLIENT = None  # lazy httpx.AsyncClient, reused across every realtime voice turn
_TURN_IDS = count(1)
_WORK_ACKS = cycle((
    "On it, sir. Give me a moment.",
    "I'll check that for you, sir.",
    "I'm on it. This may take a moment.",
))
_ONE_SENTENCE_REQUEST = re.compile(
    r"\b(?:in|to|with|as|use|give me|write|provide)\s+"
    r"(?:just\s+|only\s+)?(?:a\s+)?(?:one|single|1)\s+"
    r"(?:(?:very\s+)?(?:short|brief|concise)\s+)?sentence\b"
    r"|\b(?:one|single|1)\s+"
    r"(?:(?:very\s+)?(?:short|brief|concise)\s+)?sentence\s+(?:only|please)\b"
    r"|\b(?:just|only)\s+(?:one|single|1)\s+"
    r"(?:(?:very\s+)?(?:short|brief|concise)\s+)?sentence\b",
    re.IGNORECASE,
)


def _work_ack_delay() -> float:
    return float(CONFIG.get("voice", {}).get("work_ack_delay_sec", 1.2))


async def _construct_realtime_tts():
    from core.voice.tts import VoiceTTS
    return await asyncio.to_thread(VoiceTTS)


def start_tts_prewarm() -> asyncio.Task:
    """Reserve the realtime instance, then construct it off the event loop."""
    global _REALTIME_TTS_FUTURE
    future = _REALTIME_TTS_FUTURE
    if future is None:
        future = Future()
        _REALTIME_TTS_FUTURE = future

    async def _run():
        global _REALTIME_TTS
        if future.done():
            return
        try:
            instance = await _construct_realtime_tts()
            _REALTIME_TTS = instance
            warmup = str(CONFIG.get("voice", {}).get("tts_prewarm_text", "Ready.")).strip()
            if warmup and getattr(instance, "_kokoro_ok", False):
                await asyncio.to_thread(
                    tts_wav, warmup, float(CONFIG.get("voice", {}).get("tts_prewarm_speed", 0.85))
                )
            future.set_result(instance)
            logger.info("[VECTOR][realtime] VoiceTTS prewarm ready")
        except Exception as exc:
            logger.warning("[VECTOR][realtime] VoiceTTS prewarm failed: {}", exc)
            future.set_exception(exc)

    return asyncio.create_task(_run())


def _get_realtime_tts():
    """Return the startup instance, waiting in the TTS worker if needed."""
    global _REALTIME_TTS, _REALTIME_TTS_FUTURE
    if _REALTIME_TTS is not None and getattr(_REALTIME_TTS, "_kokoro_ok", False):
        return _REALTIME_TTS
    if _REALTIME_TTS_FUTURE is not None:
        try:
            instance = _REALTIME_TTS_FUTURE.result()
            _REALTIME_TTS_FUTURE = None
            return instance
        except Exception:
            _REALTIME_TTS_FUTURE = None
    from core.voice.tts import VoiceTTS
    _REALTIME_TTS = VoiceTTS()
    return _REALTIME_TTS


def pop_sentence(buf: str, max_chars: int = 220, *, abbreviation_aware: bool = False) -> tuple[str, str]:
    """Split off the first complete sentence from buf. Returns (sentence, rest)."""
    for i, ch in enumerate(buf):
        if ch in _SENTENCE_ENDS:
            nxt = buf[i + 1:i + 2]
            if ch == "." and nxt.isdigit():
                continue
            if ch == "." and abbreviation_aware:
                prefix = buf[:i + 1]
                following = buf[i + 1:].lstrip()
                if not nxt and prefix[-2:-1].isdigit():
                    continue
                if re.search(r"\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|St)\.$", prefix, re.I):
                    continue
                initialism = re.search(r"\b(?:[A-Za-z]\.)+$", prefix)
                if initialism and (not following or not following[0].isupper() or nxt.isalpha()):
                    continue
            return buf[:i + 1].strip(), buf[i + 1:]
    if len(buf) > max_chars:
        cut = buf.rfind(" ", 0, max_chars)
        cut = cut if cut > 0 else max_chars
        return buf[:cut].strip(), buf[cut:]
    return "", buf


def _natural_sentence_boundary(sentence: str, original_buffer: str) -> bool:
    if sentence.endswith((".", "!", "?")):
        return True
    prefix = original_buffer.lstrip()
    return prefix.startswith(sentence) and prefix[len(sentence):].lstrip(" \t").startswith("\n")


def tts_wav(text: str, speed: float = 0.85) -> bytes | None:
    """Synthesize one sentence with Kokoro -> WAV bytes. Never raises."""
    try:
        import soundfile as sf
        from core.voice.tts import sanitize_for_speech
        started = time.perf_counter()
        # 2026-07-28: this calls Kokoro directly, bypassing VoiceTTS.speak()'s
        # own sanitization — see core/voice/tts.py's module comment on
        # sanitize_for_speech() for the full story (real-time voice replies
        # were reaching TTS with raw, unstripped markdown).
        text = sanitize_for_speech(text)
        sanitized = time.perf_counter()
        if not text:
            return None
        tts = _get_realtime_tts()
        if not tts._kokoro_ok:
            return None
        voice = CONFIG.get("voice", {}).get("kokoro_voice", "bm_george")
        creation_started = time.perf_counter()
        samples, sample_rate = tts._kokoro.create(text, voice=voice, speed=speed)
        created = time.perf_counter()
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        encoded = time.perf_counter()
        logger.info(
            "[VECTOR][tts][phase0] sanitize={:.1f}ms create={:.1f}ms wav_encode={:.1f}ms",
            (sanitized - started) * 1000.0,
            (created - creation_started) * 1000.0,
            (encoded - created) * 1000.0,
        )
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[VECTOR][realtime] tts failed: {e}")
        return None


# ── Phase 4: intent classification (chat vs action) ──────────────────────────
# Phrases that mean "go do something" route to the governor; everything else
# is conversational and answered directly by the streaming LLM.

_ACTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(venture|side.?hustle|business idea)\b.*\b(pipeline|scan|search|run)\b", "venture_pipeline"),
    (r"\brun\b.*\bventure pipeline\b", "venture_pipeline"),
    (r"\b(mine|scan)\b.*\b(reddit|social|problems)\b", "mine_social"),
    (r"\b(check|show)\b.*\battendance\b", "check_attendance"),
    (r"\bgit (status|log)\b", "git_status"),
    (r"\b(commit|push)\b.*\b(code|changes|repo)\b", "git_status"),
    (r"\b(write|fix|refactor|debug|implement)\b.*\b(code|bug|function|module|test)\b", "code_task"),
    (r"\b(research|investigate|deep.?dive)\b", "daily_digest"),
    (r"\b(search|find)\b.*\b(arxiv|papers?)\b", "search_arxiv"),
    (r"\b(search|look up|google)\b", "search_web"),
    (r"\b(monitor|watch|track)\b", "monitor"),
    (r"\b(scan|audit)\b.*\b(security|repo|system)\b", "security_scan"),
    (r"\bfinance report\b|\bmonthly report\b", "monthly_report"),
    (r"\b(schedule|remind me)\b", "schedule_task"),
    (r"\b(run|execute)\b.*\b(backtest|strategy)\b", "backtest"),
    (r"\b(summarize|digest)\b.*\b(news|feeds?)\b", "daily_digest"),
]


def classify_intent(text: str) -> str | None:
    """Return a governor task type for action-like utterances, else None (chat)."""
    low = text.lower()
    for pattern, task_type in _ACTION_PATTERNS:
        if re.search(pattern, low):
            return task_type
    return None


_device_gateway = None  # module-cached PermissionGateway for voice device commands


async def try_device_action(text: str) -> str | None:
    """'open spotify'-style direct device commands from VOICE — reuses the typed
    command bar's intent detector and executes through the permission gateway
    (RULE 3 intact; proposed_by=api_command → owner speech is the confirmation).
    Scoped to launch_app, open_path, download_file, close_notifications,
    window_control, kill_app, clipboard_get/set, set_volume, set_brightness,
    lock_screen, sleep_pc, get_system_stats, read_screen_text, and
    camera_activate/camera_deactivate: search/research utterances stay
    conversational, and delete_files/shutdown_pc/restart_pc deliberately
    stay off this list (see below).
    Returns the spoken reply, or None when the utterance is not a device command."""
    global _device_gateway
    try:
        from core.api.routers.commands import _detect_intent_action
        intent = _detect_intent_action(text)
        if not intent:
            return None
        action_type = intent.get("action_type")

        if action_type in ("camera_activate", "camera_deactivate"):
            # Same gated route the Panels UI's Camera start/stop buttons and
            # the typed command bar use — not a parallel bypass (FL-031).
            from core.api.routers.camera import start_camera, stop_camera
            turning_on = action_type == "camera_activate"
            if turning_on:
                result = await start_camera(index=int(intent.get("params", {}).get("index", 0)))
            else:
                result = await stop_camera()
            if result.get("status") in ("started", "stopped"):
                return "Camera on, sir." if turning_on else "Camera off, sir."
            if result.get("status") == "blocked":
                return f"Camera {'activation' if turning_on else 'deactivation'} needs your approval — {result.get('reason', 'awaiting confirmation')}."
            return f"I couldn't {'turn on' if turning_on else 'turn off'} the camera."

        # delete_files/shutdown_pc/restart_pc are deliberately NOT handled
        # here: all three are OWNER_APPROVAL_ONLY (always block on a real
        # Pushover approval, up to 300s) — awaiting that here would freeze
        # the live voice conversation for up to 5 minutes. They already fall
        # through to the existing classify_intent()/_run_action()
        # fire-and-forget path below, which is the correct place for
        # anything that can block.
        # read_email is GREEN (always instant). create_calendar_event is
        # YELLOW, which already auto-confirms instantly for an owner-typed/
        # spoken command (see RED_INTERACTIVE_TOOLS's own docstring: this is
        # the SAME bypass YELLOW already had, which is why that set needed
        # inventing in the first place) — safe to include here too.
        # send_email deliberately stays off this list: plain RED, not
        # YELLOW or RED_INTERACTIVE_TOOLS, so it blocks on a real approval.
        _instant_types = (
            "launch_app", "open_path", "download_file", "close_notifications",
            "window_control", "kill_app", "clipboard_get", "clipboard_set",
            "set_volume", "set_brightness", "lock_screen", "sleep_pc",
            "get_system_stats", "read_screen_text",
            "read_email", "create_calendar_event",
            "word_write", "word_read", "excel_read_cell", "excel_write_cell",
            "powerpoint_create", "wmi_hardware_info", "wmi_installed_software",
        )
        if action_type not in _instant_types:
            return None
        from core.loop.permission_gateway import PermissionGateway, Action
        if _device_gateway is None:
            _device_gateway = PermissionGateway()
        result = await _device_gateway.execute(Action(
            action_type=action_type,
            params=intent.get("params", {}),
            proposed_by="api_command",
        ))
        if action_type == "read_email":
            r = result.result or {}
            if not result.executed or r.get("status") != "ok":
                err = r.get("error", "")
                return "I couldn't check your email" + (f" — {err}" if err else ".")
            msgs = r.get("messages", [])
            if not msgs:
                return "Nothing new in your inbox, sir."
            lines = "; ".join(f"{m.get('from','')}: {m.get('subject','')}" for m in msgs[:3])
            return f"You have {len(msgs)} recent message(s). {lines}"
        if action_type == "create_calendar_event":
            r = result.result or {}
            if result.executed and (r.get("id") or r.get("status") == "ok"):
                return f"Added to your calendar, sir."
            err = r.get("error", "")
            return "I couldn't add that to your calendar" + (f" — {err}" if err else ".")
        if action_type in ("word_write", "word_read", "excel_read_cell", "excel_write_cell"):
            r = result.result or {}
            ok = result.executed and ("error" not in r or r.get("ok"))
            if action_type == "word_write":
                return "Document saved, sir." if ok else f"I couldn't write that document — {r.get('error','')}"
            if action_type == "word_read":
                text = (r.get("text") or "").strip()
                return f"That document says: {text[:300]}" if ok and text else "I couldn't read that document."
            if action_type == "excel_read_cell":
                return f"That cell contains: {r.get('value')}" if ok else "I couldn't read that cell."
            if action_type == "excel_write_cell":
                return "Done, sir." if ok else f"I couldn't write that cell — {r.get('error','')}"
        if action_type == "powerpoint_create":
            r = result.result or {}
            if result.executed and r.get("ok"):
                return f"Your slides are ready, sir — {r.get('slide_count', '?')} slide(s)."
            return "I couldn't build that presentation" + (f" — {r.get('error','')}" if r.get('error') else ".")
        if action_type in ("wmi_hardware_info", "wmi_installed_software"):
            r = result.result or {}
            ok = result.executed and "error" not in r
            if action_type == "wmi_hardware_info":
                if not ok:
                    return "I couldn't read hardware info."
                gpus = ", ".join(r.get("gpus") or []) or "unknown GPU"
                return f"{r.get('manufacturer','')} {r.get('model','')}, CPU {r.get('cpu','unknown')}, {r.get('ram_gb','?')} gigs of RAM, {gpus}."
            progs = r.get("programs") or []
            if not progs:
                return "I couldn't read your installed programs."
            return f"You have {r.get('total', len(progs))} programs installed, sir."
        if action_type in (
            "window_control", "kill_app", "clipboard_get", "clipboard_set",
            "set_volume", "set_brightness", "lock_screen", "sleep_pc",
            "get_system_stats", "read_screen_text",
        ):
            r = result.result or {}
            ok = result.executed and r.get("status") == "ok"
            if action_type == "window_control":
                return (f"Done, sir." if ok else "I couldn't do that" + (f" — {r.get('error','')}" if r.get('error') else "."))
            if action_type == "kill_app":
                n = len(r.get("killed") or [])
                return (f"Closed it, sir." if ok and n else "Nothing matching that was running, sir." if ok else
                        f"I couldn't close that" + (f" — {r.get('error','')}" if r.get('error') else "."))
            if action_type == "clipboard_get":
                return (f"Your clipboard has: {r.get('text','')}" if ok else "I couldn't read the clipboard.")
            if action_type == "clipboard_set":
                return ("Copied to clipboard, sir." if ok else "I couldn't set the clipboard.")
            if action_type == "set_volume":
                return ("Done, sir." if ok else "I couldn't change the volume.")
            if action_type == "set_brightness":
                return ("Done, sir." if ok else "I couldn't change the brightness.")
            if action_type == "lock_screen":
                return ("Locking the screen now, sir." if ok else "I couldn't lock the screen.")
            if action_type == "sleep_pc":
                return ("Putting the machine to sleep, sir." if ok else "I couldn't put it to sleep.")
            if action_type == "get_system_stats":
                if not ok:
                    return "I couldn't read system stats."
                return (f"CPU {r.get('cpu_percent','?')}%, memory {r.get('memory_percent','?')}%, "
                        f"disk {r.get('disk_percent','?')}%.")
            if action_type == "read_screen_text":
                txt = (r.get("text") or "").strip()
                return (f"The screen shows: {txt[:300]}" if ok and txt else
                        "I couldn't find readable text on screen." if ok else "I couldn't read the screen.")

        if action_type == "open_path":
            target = str(intent.get("params", {}).get("path", "that"))
            if result.executed and (result.result or {}).get("status") == "ok":
                return f"Opened {target}, sir."
            err = (result.result or {}).get("error", "")
            return f"I couldn't open {target}" + (f" — {err}" if err else ".")
        if action_type == "download_file":
            if result.executed and (result.result or {}).get("status") == "ok":
                dest = (result.result or {}).get("dest", "")
                return f"Downloaded, sir." + (f" Saved to {dest}." if dest else "")
            err = (result.result or {}).get("error", "")
            return "I couldn't download that" + (f" — {err}" if err else ".")
        if action_type == "close_notifications":
            if result.executed and (result.result or {}).get("status") == "ok":
                return "Notifications cleared, sir."
            err = (result.result or {}).get("error", "")
            return "I couldn't clear notifications" + (f" — {err}" if err else ".")
        app = str(intent.get("params", {}).get("app_name", "the app"))
        if result.executed and (result.result or {}).get("status") == "ok":
            return f"Opening {app}, sir."
        err = (result.result or {}).get("error", "")
        return f"I couldn't open {app}" + (f" — {err}" if err else ".")
    except Exception as e:
        logger.warning(f"[VECTOR][realtime] device action failed: {e}")
        return None


# Cheap prefilter for the LLM intent gate: only utterances containing an
# imperative-ish verb are worth an LLM round-trip. Pure conversation
# ("good morning", "how are you") skips the gate — zero added latency.
_ACTION_VERB_HINTS = frozenset(
    "run execute make create generate build check scan search find get fetch "
    "send schedule remind monitor watch track report fix write code deploy "
    "update upload download start stop open close analyze analyse summarize "
    "summarise research investigate review audit test commit push publish "
    "record translate convert install delete rename backup sync mine".split()
)


def _needs_llm_intent(text: str) -> bool:
    return bool(set(re.findall(r"[a-z']+", text.lower())) & _ACTION_VERB_HINTS)


def classify_intent_llm(text: str) -> str | None:
    """LLM chat-vs-action fallback when the regex patterns miss.

    Asks vector-focus (permanent VRAM — no model thrash with
    OLLAMA_MAX_LOADED_MODELS=1) whether the utterance is a command.
    Returns a short natural-language task type — Governor.route_task() accepts
    natural language (keyword map + its own LLM district classifier) — or None
    for conversation / any failure. Gated by CONFIG voice.llm_intent_fallback.
    """
    try:
        if not _needs_llm_intent(text):
            return None
        from core.config import CONFIG
        voice_cfg = CONFIG.get("voice", {})
        if not voice_cfg.get("llm_intent_fallback", True):
            return None
        from core.inference.ollama_safe import chat
        prompt = (
            "Is this utterance a COMMAND to perform work, or conversation?\n"
            "Reply one line: CHAT or ACTION: <3-6 word task>\n"
            f'Utterance: "{text}"'
        )
        # focus, not ambient: vector-ambient's modelfile forces JSON-only
        # output (it puts answers in `thinking` with empty content), and
        # loading it would evict the resident focus model (MAX_LOADED=1).
        # think=False: focus is a thinking model; without it, ~100 hidden
        # reasoning tokens push a one-line answer to ~7s (2s with it off).
        # Cloud primary, Ollama fallback (owner policy 2026-07-02): the API
        # keys are faster than local prefill for a one-line classification and
        # never touch the GPU the owner's coding model may occupy. route_policy
        # still forces secret-looking utterances local-only. pytest stays
        # local/mocked — no network in tests.
        result = ""
        if "pytest" not in sys.modules:
            try:
                import concurrent.futures as _cf
                from core.inference.provider_client import get_client

                def _cloud():
                    return get_client().complete_sync(
                        prompt, tier="fast", temperature=0.0, max_tokens=32,
                        caller_id="voice_intent")

                # Hard budget: a failing-provider cascade (cooldowns, retries)
                # must not stall the voice loop — abandon cloud and go local.
                # No `with` block: executor shutdown would join the abandoned
                # thread and block for the full cascade anyway.
                _ex = _cf.ThreadPoolExecutor(max_workers=1)
                try:
                    _res = _ex.submit(_cloud).result(
                        timeout=float(voice_cfg.get("llm_intent_cloud_budget_sec", 8.0)))
                    result = (_res.content or "").strip()
                    if result:
                        logger.debug(f"[VECTOR][realtime] intent gate served by {_res.provider}")
                finally:
                    _ex.shutdown(wait=False, cancel_futures=True)
            except Exception as _cf_err:
                logger.debug(f"[VECTOR][realtime] cloud intent gate failed/over budget: {_cf_err}")
        if not result:
            result = chat(
                model=CONFIG["models"]["focus"],
                messages=[{"role": "user", "content": prompt}],
                timeout=float(voice_cfg.get("llm_intent_timeout_sec", 12.0)),
                temperature=0.0,
                think=False,
                num_predict=32,
                caller_id="voice_intent",
            ).strip()
        if not result:
            return None
        # Robust extraction — persona may prefix ("Sir, ACTION: ...").
        first_line = result.splitlines()[0].strip()
        m = re.search(r"\bACTION\s*:\s*(.+)", first_line, re.IGNORECASE)
        if m:
            task_type = m.group(1).strip().strip('."')
            # Sanity clamp — a task type is a short phrase, not an essay.
            if 0 < len(task_type) <= 80:
                logger.info(f"[VECTOR][realtime] LLM intent: ACTION '{task_type}' <- {text[:60]!r}")
                return task_type
        return None
    except Exception as e:
        logger.warning(f"[VECTOR][realtime] LLM intent fallback failed (treating as chat): {e}")
        return None


def _in_quiet_hours(now_minutes: int, spec: str) -> bool:
    """spec '23:30-07:00' (may wrap midnight). Empty spec -> never quiet."""
    try:
        if not spec or "-" not in spec:
            return False
        a, b = spec.split("-", 1)
        ah, am = (int(x) for x in a.strip().split(":"))
        bh, bm = (int(x) for x in b.strip().split(":"))
        start, end = ah * 60 + am, bh * 60 + bm
        if start == end:
            return False
        if start < end:
            return start <= now_minutes < end
        return now_minutes >= start or now_minutes < end  # wraps midnight
    except Exception:
        return False


class RealtimeConversation:
    """One full-duplex voice session. Feed PCM in; JSON events come out."""

    def __init__(self, send_json, orb=None):
        self._send = send_json                  # async callable(dict)
        self._orb = orb                         # async callable(str) | None
        voice_cfg = CONFIG.get("voice", {})
        self._sr = 16000
        self._max_utterance_samples = int(float(voice_cfg.get("max_utterance_sec", 30.0)) * self._sr)
        self._utterance_samples = 0
        self._endpoint_ms = int(voice_cfg.get("endpoint_silence_ms", 650))
        self._bargein = bool(voice_cfg.get("bargein_enabled", True))
        self._bargein_debounce_ms = int(voice_cfg.get("bargein_debounce_ms", 120))
        self._partial_interval = float(voice_cfg.get("partial_interval_sec", 0.6))
        self._proactive = bool(voice_cfg.get("proactive_speech", True))
        self._proactive_min_priority = float(voice_cfg.get("proactive_min_priority", 0.7))
        self._quiet_hours = str(voice_cfg.get("quiet_hours", "00:00-08:00"))

        from core.voice.conversation_manager import ConversationManager
        self._conv = ConversationManager()

        from core.voice.vad import VoiceActivityDetector
        self._vad = VoiceActivityDetector()
        self._vad._min_silence_ms = self._endpoint_ms      # realtime endpointing
        self._base_vad_threshold = self._vad._energy_threshold

        self._stt = None                        # lazy — model load is heavy
        self._utterance: list[np.ndarray] = []
        self._utterance_started = 0.0
        self._last_partial = 0.0
        self._partial_audio_samples = 0
        self._partial_busy = False
        self._client_playing = False            # echo guard flag from client
        self._bargein_speech_ms = 0.0
        self._bargein_ready = True
        self._speak_task: asyncio.Task | None = None
        self._cancel_speak = asyncio.Event()
        self._nudge_unsub = None
        self._closed = False
        self._speaker_owner = True   # last utterance verified as owner?

        # Phase 6 — session idle timeout → IDLE, wake word resumes (design §6)
        self._conversation_timeout = float(voice_cfg.get("conversation_timeout_sec", 30))
        self._last_activity = time.monotonic()
        self._wake_detector = None
        self._wake_failed = False
        self._wake_buffer: list[np.ndarray] = []
        self._wake_buffer_ms = 0.0
        self._wake_busy = False
        self._latency_turn_id = ""
        self._latency_turn_start = 0.0
        self._latency_last = 0.0
        self._interactive_session_active = False

    def _start_latency_turn(self) -> str:
        self._latency_turn_id = f"rt{next(_TURN_IDS)}"
        self._latency_turn_start = time.monotonic()
        self._latency_last = self._latency_turn_start
        return self._latency_turn_id

    def _latency_mark(self, stage: str) -> None:
        if not self._latency_turn_id:
            return
        now = time.monotonic()
        logger.info(
            "[VECTOR][realtime][latency] turn={} stage={} delta_ms={:.1f} total_ms={:.1f}",
            self._latency_turn_id,
            stage,
            (now - self._latency_last) * 1000.0,
            (now - self._latency_turn_start) * 1000.0,
        )
        self._latency_last = now

    def _begin_voice_priority(self) -> None:
        if self._interactive_session_active:
            return
        from core.inference.ollama_priority import begin_interactive_session
        begin_interactive_session(caller_id="realtime_voice_utterance")
        self._interactive_session_active = True

    def _end_voice_priority(self) -> None:
        if not self._interactive_session_active:
            return
        from core.inference.ollama_priority import end_interactive_session
        end_interactive_session(caller_id="realtime_voice_utterance")
        self._interactive_session_active = False

    # ── session ──────────────────────────────────────────────────────────────

    async def start(self, user_id: str = "owner") -> None:
        self._conv.start_session(user_id)
        self._conv.transition("LISTENING")
        await self._state("LISTENING")
        if self._proactive:
            self._subscribe_nudges()
        logger.info("[VECTOR][realtime] session started")

    async def stop(self) -> None:
        self._closed = True
        await self._cancel_speaking()
        # If the socket drops mid-utterance (USER_SPEAKING already called
        # _begin_voice_priority(), but endpoint-silence never fired so
        # _finalize_utterance()'s finally never ran), the interactive flag
        # would otherwise leak true forever, starving background Ollama
        # callers. _end_voice_priority() is idempotent, safe to call here
        # unconditionally.
        self._end_voice_priority()
        if self._nudge_unsub:
            try:
                self._nudge_unsub()
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
            self._nudge_unsub = None
        self._conv.end_session()
        logger.info("[VECTOR][realtime] session ended")

    def set_client_playing(self, playing: bool) -> None:
        """Echo guard: client reports speaker playback; raise VAD threshold."""
        self._client_playing = playing
        self._vad._energy_threshold = (
            self._base_vad_threshold * 2.5 if playing else self._base_vad_threshold
        )

    # ── audio in (Phase 2 + Phase 3) ─────────────────────────────────────────

    async def feed_pcm(self, pcm_bytes: bytes) -> None:
        """One int16 mono 16kHz frame from the client (~20-130ms)."""
        if self._closed or not pcm_bytes:
            return
        frame = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        frame_ms = len(frame) / self._sr * 1000.0
        is_speech = self._vad.is_speech(frame, self._sr)
        state = str(self._conv.current_state)

        # Phase 6 — IDLE: only the wake word gets us out
        if state == "IDLE":
            await self._idle_frame(frame, is_speech)
            return

        # Idle timer: anything except quiet LISTENING counts as activity
        if is_speech or state != "LISTENING":
            self._last_activity = time.monotonic()
        elif (self._conversation_timeout > 0
              and (time.monotonic() - self._last_activity) >= self._conversation_timeout):
            await self._go_idle()
            return

        # Phase 3 — barge-in: user speaks while VECTOR is speaking
        if state == "VECTOR_SPEAKING":
            if not is_speech:
                self._bargein_ready = True
            if self._bargein and self._bargein_ready and is_speech:
                self._bargein_speech_ms += frame_ms
                if self._bargein_speech_ms >= self._bargein_debounce_ms:
                    await self._barge_in(frame)
            else:
                self._bargein_speech_ms = 0.0
            return

        if state == "PROCESSING":
            self._bargein_ready = not is_speech
            return  # ignore audio while thinking (next phase could queue it)

        # Phase 2 — endpointing
        if is_speech:
            if state == "LISTENING":
                self._begin_voice_priority()
                self._conv.transition("USER_SPEAKING")
                await self._state("USER_SPEAKING")
                self._utterance = []
                self._utterance_samples = 0
                self._utterance_started = time.monotonic()
                self._last_partial = time.monotonic()
                self._partial_audio_samples = 0
            self._utterance.append(frame)
            self._utterance_samples += len(frame)
            if self._utterance_samples >= self._max_utterance_samples:
                audio = np.concatenate(self._utterance)
                self._utterance = []
                self._utterance_samples = 0
                self._start_latency_turn()
                self._latency_mark("max_utterance_endpoint")
                self._conv.transition("PROCESSING")
                await self._state("PROCESSING")
                asyncio.create_task(self._finalize_utterance(audio))
                return
            # Schedule by captured audio, independent of frame delivery speed.
            self._partial_audio_samples += len(frame)
            if (self._partial_audio_samples >= self._partial_interval * self._sr
                    and not self._partial_busy):
                self._partial_audio_samples = 0
                self._last_partial = time.monotonic()
                asyncio.create_task(self._partial_decode())
        elif state == "USER_SPEAKING":
            self._utterance.append(frame)        # trailing context for STT
            # VAD flipped back to SILENCE == endpoint reached
            if self._vad.state == "SILENCE":
                audio = np.concatenate(self._utterance) if self._utterance else np.zeros(0)
                self._utterance = []
                self._start_latency_turn()
                self._latency_mark("vad_endpoint_detected")
                self._conv.transition("PROCESSING")
                await self._state("PROCESSING")
                asyncio.create_task(self._finalize_utterance(audio))

    async def _barge_in(self, seed_frame: np.ndarray) -> None:
        logger.info("[VECTOR][realtime] barge-in — interrupting")
        self._bargein_speech_ms = 0.0
        self._conv.interrupt()                   # VECTOR_SPEAKING -> INTERRUPTED
        await self._cancel_speaking()
        await self._safe_send({"type": "stop_audio"})
        self._conv.transition("LISTENING")
        await self._state("LISTENING")
        # the speech that triggered the interrupt starts the next utterance
        self._begin_voice_priority()
        self._conv.transition("USER_SPEAKING")
        await self._state("USER_SPEAKING")
        self._utterance = [seed_frame]
        self._utterance_samples = len(seed_frame)
        self._utterance_started = time.monotonic()
        self._last_partial = time.monotonic()
        self._partial_audio_samples = 0

    # ── Phase 6: idle timeout + wake-word resume ──────────────────────────────

    async def _go_idle(self) -> None:
        logger.info("[VECTOR][realtime] no speech for {:.0f}s — IDLE (say 'Vector' to resume)",
                    self._conversation_timeout)
        self._utterance = []
        self._wake_buffer = []
        self._wake_buffer_ms = 0.0
        await self._cancel_speaking()
        self._conv.transition("IDLE")
        await self._state("IDLE")

    def _get_wake(self):
        """Lazy WakeWordDetector; None when unavailable (STT fallback handles wake)."""
        if self._wake_detector is None and not self._wake_failed:
            try:
                from core.voice.wake_word import WakeWordDetector
                self._wake_detector = WakeWordDetector()
            except Exception as e:
                logger.warning(f"[VECTOR][realtime] wake detector unavailable: {e}")
                self._wake_failed = True
        return self._wake_detector

    async def _idle_frame(self, frame: np.ndarray, is_speech: bool) -> None:
        """While IDLE, scan incoming frames for the wake word."""
        det = self._get_wake()
        if det is not None and det._model is not None and not det._use_whisper_kws:
            int16 = (frame * 32767.0).astype(np.int16)
            if det.is_wake_word(int16):
                await self._wake_up()
            return

        # Fallback (no openwakeword): buffer one speech burst, STT it once,
        # look for the wake phrase. Reuses the session's lazy STT.
        if is_speech:
            self._wake_buffer.append(frame)
            self._wake_buffer_ms += len(frame) / self._sr * 1000.0
            if self._wake_buffer_ms >= 2500:
                await self._check_wake_buffer()
        elif self._wake_buffer and self._vad.state == "SILENCE":
            await self._check_wake_buffer()

    async def _check_wake_buffer(self) -> None:
        if self._wake_busy:
            self._wake_buffer = []
            self._wake_buffer_ms = 0.0
            return
        audio = np.concatenate(self._wake_buffer) if self._wake_buffer else np.zeros(0)
        self._wake_buffer = []
        self._wake_buffer_ms = 0.0
        if audio.size < self._sr * 0.3:
            return
        stt = self._get_stt()
        if stt is None:
            return
        self._wake_busy = True
        try:
            text = (await asyncio.to_thread(stt.transcribe, audio, self._sr)).lower().strip()
            if "vector" in text or "vektor" in text:
                await self._wake_up()
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] wake KWS decode failed: {e}")
        finally:
            self._wake_busy = False

    async def _wake_up(self) -> None:
        logger.info("[VECTOR][realtime] wake word detected — resuming")
        self._last_activity = time.monotonic()
        self._wake_buffer = []
        self._wake_buffer_ms = 0.0
        self._conv.transition("LISTENING")
        await self._safe_send({"type": "wake"})
        await self._state("LISTENING")

    # ── STT (Phase 2) ─────────────────────────────────────────────────────────

    def _get_stt(self):
        if self._stt is None:
            voice_cfg = CONFIG.get("voice", {})
            realtime_model = voice_cfg.get("realtime_stt_model", "small")
            try:
                from core.voice.stt import FasterWhisperSTT
                stt = FasterWhisperSTT()
            except Exception:
                from core.voice.stt import WhisperSTT
                stt = WhisperSTT()
            stt._model_name = realtime_model     # latency choice, see design §11
            self._stt = stt
        return self._stt

    async def _partial_decode(self) -> None:
        if self._partial_busy or not self._utterance:
            return
        self._partial_busy = True
        try:
            audio = np.concatenate(self._utterance)
            text = await asyncio.to_thread(self._get_stt().transcribe, audio, self._sr)
            if text and str(self._conv.current_state) == "USER_SPEAKING":
                await self._safe_send({"type": "partial_transcript", "text": text})
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] partial decode skipped: {e}")
        finally:
            self._partial_busy = False

    async def _finalize_utterance(self, audio: np.ndarray) -> None:
        if not self._latency_turn_id:
            self._start_latency_turn()
        self._latency_mark("finalize_entry")
        # Mark owner-facing Ollama demand for the WHOLE turn (STT ->
        # speaker-verify -> LLM generation), not just the LLM call at the
        # end of it. acquire_interactive() alone only covers
        # _stream_ollama_tokens() -- STT transcription and speaker
        # verification both run first and can themselves take seconds,
        # during which a background Ollama caller saw no interactive
        # demand yet and could win the single-model-slot race moments
        # before this turn's own LLM call needs it. See
        # ollama_priority.begin_interactive_session()'s docstring for the
        # live-observed symptom this closes (8-35s instead of ~2s warm).
        self._begin_voice_priority()
        try:
            if audio.size < self._sr // 4:       # <250ms of audio — noise blip
                self._back_to_listening()
                await self._state("LISTENING")
                return
            self._latency_mark("stt_transcribe_start")
            text = await asyncio.to_thread(self._get_stt().transcribe, audio, self._sr)
            self._latency_mark("stt_transcribe_done")
            text = (text or "").strip()
            if not text:
                self._back_to_listening()
                await self._state("LISTENING")
                return
            await self._safe_send({"type": "final_transcript", "text": text})

            # prompt-injection scan before the text reaches any LLM (design §11)
            try:
                from core.security.prompt_injection import scan_text
                if not scan_text(text, "realtime_voice").clean:
                    await self._speak_text("I'm not acting on that input.")
                    self._back_to_listening()
                    await self._state("LISTENING")
                    return
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass

            # Speaker verification — only the enrolled owner can command actions.
            # Fails open when not enrolled (see speaker_verify.py); every
            # decision is surfaced to the HUD as a "speaker" event.
            self._speaker_owner = True
            try:
                from core.voice.speaker_verify import get_verifier
                self._latency_mark("speaker_verify_start")
                _v = get_verifier()
                if _v.active:
                    self._speaker_owner, _sim = await asyncio.to_thread(
                        _v.verify, audio, self._sr)
                    self._latency_mark("speaker_verify_done")
                    await self._safe_send({"type": "speaker",
                                           "owner": self._speaker_owner,
                                           "similarity": round(_sim, 3)})
                    if not self._speaker_owner:
                        logger.warning(
                            "[VECTOR][realtime] unverified speaker (sim={:.3f})", _sim)
                else:
                    self._latency_mark("speaker_verify_done")
            except Exception as _sv_err:
                self._latency_mark("speaker_verify_done")
                logger.debug(f"[VECTOR][realtime] speaker verify skipped: {_sv_err}")

            self._latency_mark("respond_entry")
            await self._respond(text)
        except Exception as e:
            logger.error(f"[VECTOR][realtime] finalize failed: {e}")
            self._back_to_listening()
            await self._state("LISTENING")
        finally:
            self._end_voice_priority()

    def _back_to_listening(self) -> None:
        cur = str(self._conv.current_state)
        if cur != "LISTENING":
            self._conv.transition("LISTENING")

    # ── respond (Phases 1+4) ──────────────────────────────────────────────────

    async def _respond(self, text: str) -> None:
        self._cancel_speak.clear()
        self._work_ack_this_turn = False
        # 1. rules-engine bypass — instant, no LLM
        try:
            from core.security.rules_engine import get_rules_engine
            engine = get_rules_engine()
            rule = engine.match(text)
            if rule:
                answer = engine.execute_rule(rule, {}) or "Done."
                await self._safe_send({"type": "response", "text": answer})
                await self._speak_text(answer)
                self._store_turn(text, answer, ["bypass", rule.category])
                self._back_to_listening()
                await self._state("LISTENING")
                return
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] rules bypass skipped: {e}")

        # 1.6 Direct device command ("open spotify") — same detector as the typed
        # command bar, executed via the permission gateway. Owner voice only.
        if self._speaker_owner:
            try:
                device_reply = await try_device_action(text)
            except Exception:
                device_reply = None
            if device_reply is not None:
                await self._safe_send({"type": "response", "text": device_reply})
                await self._speak_text(device_reply)
                self._store_turn(text, device_reply, ["device_action"])
                self._back_to_listening()
                await self._state("LISTENING")
                return

        # 2. Phase 4 — action handoff to governor (RULE 3: gateway untouched)
        task_type = classify_intent(text)
        if task_type is None and _needs_llm_intent(text):
            # Regex miss → LLM chat-vs-action gate (ambient model, off-thread so
            # the event loop keeps streaming). Governor.route_task() handles the
            # natural-language task type it returns.
            intent_started = time.monotonic()
            intent_task = asyncio.create_task(asyncio.to_thread(classify_intent_llm, text))
            done, _ = await asyncio.wait({intent_task}, timeout=_work_ack_delay())
            if not done:
                await self._send_work_ack()
            task_type = await intent_task
            logger.info("[VECTOR][realtime][latency] intent_gate_ms={:.1f} ack={}",
                        (time.monotonic() - intent_started) * 1000, not bool(done))
        if task_type and not self._speaker_owner:
            refusal = ("Voice not recognized — action commands are owner-only. "
                       "We can still chat.")
            await self._safe_send({"type": "response", "text": refusal})
            await self._speak_text(refusal)
            self._store_turn(text, refusal, ["security", "speaker_rejected"])
            self._back_to_listening()
            await self._state("LISTENING")
            return
        if task_type:
            asyncio.create_task(self._run_action(task_type, text))
            await self._publish_voice_event(text, task_type)
            self._back_to_listening()
            await self._state("LISTENING")
            return

        # 3. chat — streaming LLM -> sentence TTS
        self._cancel_speak.clear()
        self._latency_mark("stream_chat_task_create")
        self._speak_task = asyncio.create_task(self._stream_chat(text))
        try:
            await self._speak_task
        except asyncio.CancelledError:
            logger.info("[VECTOR][realtime] speak task cancelled (barge-in)")
        finally:
            self._speak_task = None
            if str(self._conv.current_state) == "VECTOR_SPEAKING":
                self._conv.transition("LISTENING")
                await self._state("LISTENING")
            await self._safe_send({"type": "done"})

    async def _send_work_ack(self) -> bool | None:
        if getattr(self, "_work_ack_this_turn", False):
            return None
        self._work_ack_this_turn = True
        ack = next(_WORK_ACKS)
        await self._safe_send({"type": "action_ack", "task_type": "processing", "text": ack})
        await self._speak_text(ack)
        if self._cancel_speak.is_set():
            # Interrupted mid-ack: a barge-in already moved the FSM to the
            # new utterance (USER_SPEAKING). Forcing our own transitions
            # here would clobber that state out from under it.
            return False
        # Standalone speech returns to LISTENING. A pending classifier or
        # streaming answer still needs the FSM in PROCESSING.
        self._conv.transition("USER_SPEAKING")
        self._conv.transition("PROCESSING")
        await self._state("PROCESSING")
        return True

    async def _stream_chat(self, text: str) -> None:
        self._latency_mark("stream_chat_entry")
        one_sentence = bool(_ONE_SENTENCE_REQUEST.search(text))
        speed = 0.85
        system_prompt = ""
        try:
            if CONFIG.get("personality", {}).get("enabled", True):
                from core.personality import PersonalityEngine
                if not hasattr(RealtimeConversation, "_pe"):
                    RealtimeConversation._pe = PersonalityEngine()
                result = RealtimeConversation._pe.process(text)
                sp = result.get("system_prompt", "")
                tone = result.get("tone_config")
                if tone:
                    speed = tone.speed
                if sp:
                    system_prompt = sp
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] personality skipped: {e}")

        # 2026-07-29 CORRECTION (issue #37): `core.personality` DOES exist and
        # DOES work — the try/except above normally succeeds and returns a
        # real, non-empty system_prompt built from
        # core/personality/characters/vector.json's `rules` array. The actual
        # root cause of the Hindi-leak / markdown-in-speech bug was that
        # vector.json's rules never included an English-only or
        # spoken-text-safety directive, so PersonalityEngine's real output was
        # missing that guidance (this fallback almost never engaged). Fixed at
        # the source: vector.json's rules array now includes both directives,
        # so every PersonalityEngine consumer gets them automatically. This
        # fallback stays as a defense-in-depth safety net for the case where
        # personality is disabled/unavailable — same VECTOR_PERSONALITY used
        # by the other voice pipeline (ambient_listener.py).
        if not system_prompt:
            try:
                from core.voice.ambient_listener import VECTOR_PERSONALITY
                system_prompt = VECTOR_PERSONALITY
            except Exception as e:
                logger.warning(f"[VECTOR][realtime] VECTOR_PERSONALITY fallback failed: {e}")
                system_prompt = (
                    "You are VECTOR, Arghyadeep's personal AI assistant. Always "
                    "respond in English regardless of what language the user's "
                    "message is written in. This reply will be read aloud by "
                    "text-to-speech — plain natural spoken sentences only, no "
                    "markdown, no spelled-out punctuation names."
                )
        if one_sentence:
            system_prompt += (
                "\nFor this reply, honor the user's explicit length request: "
                "answer directly in one short spoken sentence, without extra context or follow-up."
            )

        full, buf, seq = "", "", 0
        speaking = False
        checked_first_sentence = False
        # response_partial was sent on EVERY token -- each is a real await on
        # the injected send_json callback (actual WebSocket frame send, not
        # free). Live-measured 2026-10-14: a 50-100 token reply means 50-100
        # sequential sends *inside* the token-generation loop (the `async
        # for` can't pull the next token until each send's await resolves),
        # which can add up to real seconds before the first sentence is even
        # complete -- this was a strong, previously-unidentified contributor
        # to the gap between isolated raw-generation benchmarks (~1.2s) and
        # the actual live round trip (~6-8s even warm). Throttled the same
        # way _partial_decode()'s STT partials already are (self._partial_interval,
        # ~line 417) -- always still sent at a sentence boundary (that's
        # when _emit_sentence()/TTS fires, so that path must not be stale),
        # just not on every single intermediate token.
        last_partial_sent = 0.0
        first_token_seen = False

        # Realtime voice needs true token streaming so sentence 1 can be spoken
        # while the local model is still generating sentence 2+. ProviderClient
        # deliberately uses non-streaming cloud calls today, so this narrow path
        # stays on local Ollama until ProviderClient grows a shared streaming API.
        stream = self._stream_ollama_tokens(text, system_prompt)
        first_task = asyncio.create_task(anext(stream, None))
        try:
            done, _ = await asyncio.wait({first_task}, timeout=_work_ack_delay())
            if not done and not getattr(self, "_work_ack_this_turn", False):
                if await self._send_work_ack() is False:
                    # Interrupted mid-ack: a barge-in already took over the
                    # turn. Don't keep waiting on the stale first token.
                    first_task.cancel()
                    with contextlib.suppress(BaseException):
                        await first_task
                    await stream.aclose()
                    return
            first_token = await first_task
            logger.info("[VECTOR][realtime][latency] first_token_ack={} ",
                        getattr(self, "_work_ack_this_turn", False))
        except BaseException:
            if not first_task.done():
                first_task.cancel()
            raise

        async def _tokens():
            if first_token is not None:
                yield first_token
            async for next_token in stream:
                yield next_token

        try:
            async for token in _tokens():
                if self._cancel_speak.is_set():
                    return
                if not first_token_seen:
                    first_token_seen = True
                    self._latency_mark("first_ollama_token_received")
                full += token
                buf += token
                original_buffer = buf
                sentence, buf = pop_sentence(buf, abbreviation_aware=one_sentence)
                reached_limit = one_sentence and bool(sentence) and _natural_sentence_boundary(
                    sentence, original_buffer
                )
                if reached_limit:
                    if buf:
                        full = full[:-len(buf)]
                    full = full.strip()
                    buf = ""
                now = time.monotonic()
                if sentence or (now - last_partial_sent) >= self._partial_interval:
                    await self._safe_send({"type": "response_partial", "text": full})
                    last_partial_sent = now
                if sentence:
                    self._latency_mark("first_sentence_popped" if seq == 0 else "sentence_popped")
                    if not checked_first_sentence:
                        checked_first_sentence = True
                        try:
                            from core.city.governor import _ensure_english_response, _is_mostly_devanagari
                            if _is_mostly_devanagari(sentence):
                                sentence = await _ensure_english_response(sentence)
                        except Exception as e:
                            logger.warning(f"[VECTOR][realtime] English-only first-sentence check skipped: {e}")
                    if not speaking:
                        speaking = True
                        self._conv.transition("VECTOR_SPEAKING")
                        await self._state("VECTOR_SPEAKING")
                    await self._emit_sentence(sentence, speed, seq)
                    seq += 1
                if reached_limit:
                    break
        finally:
            await stream.aclose()

        tail = buf.strip()
        if tail and not self._cancel_speak.is_set():
            if not speaking:
                self._conv.transition("VECTOR_SPEAKING")
                await self._state("VECTOR_SPEAKING")
            await self._emit_sentence(tail, speed, seq)
        if full.strip():
            await self._safe_send({"type": "response", "text": full.strip()})
            self._store_turn(text, full.strip(), ["chat", "realtime"])

    async def _stream_ollama_tokens(self, text: str, system_prompt: str) -> AsyncIterator[str]:
        import httpx
        from core.loop.context_engine import ContextEngine

        ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
        model = CONFIG.get("models", {}).get("focus", "vector-focus")
        try:
            self._latency_mark("hydration_start")
            hydration = ContextEngine().session_hydration_prompt({"query": text})
            self._latency_mark("hydration_done")
        except Exception as e:
            self._latency_mark("hydration_done")
            logger.warning(f"[VECTOR][realtime] session hydration failed: {e}")
            hydration = ""
        prompt_parts = [part for part in (system_prompt, hydration, f"User: {text}") if part]
        prompt = "\n\n".join(prompt_parts)

        from core.inference.ollama_priority import acquire_interactive

        global _OLLAMA_STREAM_CLIENT
        # Constructing a fresh httpx.AsyncClient per call measured ~183ms of
        # pure setup/teardown overhead (connection pool, transport init) on
        # every single voice turn -- reuse one client for the process
        # lifetime instead, the same way Kokoro (_REALTIME_TTS) is reused
        # above. Safe to share across concurrent calls within one event
        # loop (httpx's own designed use case); never explicitly closed --
        # matches Ollama's own keep_alive=-1 models staying resident.
        if _OLLAMA_STREAM_CLIENT is None:
            _OLLAMA_STREAM_CLIENT = httpx.AsyncClient(timeout=60.0)
        client = _OLLAMA_STREAM_CLIENT

        async with acquire_interactive(caller_id="realtime_voice_stream", model=model):
            self._latency_mark("ollama_stream_request_start")
            async with client.stream(
                "POST",
                f"{ollama_host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True,
                    "think": False,
                    "keep_alive": -1,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 512,
                    },
                },
            ) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"ollama status {r.status_code}")
                self._latency_mark("ollama_stream_response_headers")
                async for line in r.aiter_lines():
                    if self._cancel_speak.is_set():
                        return
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = payload.get("response", "")
                    if token:
                        yield token
                    if payload.get("done"):
                        fields = ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_count", "eval_count")
                        if all(isinstance(payload.get(field), (int, float)) and not isinstance(payload.get(field), bool) and payload[field] >= 0 for field in fields):
                            logger.info(
                                "[VECTOR][ollama][phase0] total={:.1f}ms load={:.1f}ms prompt_eval={:.1f}ms ({} tokens) eval={:.1f}ms ({} tokens)",
                                payload["total_duration"] / 1_000_000,
                                payload["load_duration"] / 1_000_000,
                                payload["prompt_eval_duration"] / 1_000_000,
                                payload["prompt_eval_count"],
                                payload["eval_duration"] / 1_000_000,
                                payload["eval_count"],
                            )
                        break

    async def _emit_sentence(self, sentence: str, speed: float, seq: int) -> None:
        if self._cancel_speak.is_set():
            return
        self._latency_mark("emit_sentence_entry")
        wav = await asyncio.to_thread(tts_wav, sentence, speed)
        self._latency_mark("kokoro_tts_done")
        if wav and not self._cancel_speak.is_set():
            await self._safe_send({
                "type": "audio",
                "data": base64.b64encode(wav).decode(),
                "sample_rate": 24000,
                "seq": seq,
            })
            self._latency_mark("ws_audio_send_done")

    async def _speak_text(self, text: str) -> None:
        """Speak a short standalone line (ack / nudge / bypass answer)."""
        prev = str(self._conv.current_state)
        if prev == "IDLE":
            # FSM: IDLE only allows LISTENING — step through it first
            self._conv.transition("LISTENING")
            prev = "LISTENING"
        if prev in ("LISTENING", "PROCESSING"):
            # FSM only allows VECTOR_SPEAKING from PROCESSING
            if prev != "PROCESSING":
                self._conv.transition("USER_SPEAKING")
                self._conv.transition("PROCESSING")
            self._conv.transition("VECTOR_SPEAKING")
            await self._state("VECTOR_SPEAKING")
        await self._emit_sentence(text, 0.85, 0)
        self._last_activity = time.monotonic()   # don't instantly re-idle after speaking
        if str(self._conv.current_state) == "VECTOR_SPEAKING":
            self._conv.transition("LISTENING")
            await self._state("LISTENING")

    # ── Phase 4: governor handoff ─────────────────────────────────────────────

    async def _run_action(self, task_type: str, text: str) -> None:
        # RR-3.7C (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        # RR3_7C_FINAL_INGRESS_AUTHORIZATION_FREEZE_REPORT.md): this used to
        # call Governor().dispatch() DIRECTLY -- zero Candidate, zero
        # DecisionEngine.evaluate(), zero PermissionGateway.execute() -- the
        # exact same bypass shape RR-3.6 already found and fixed for
        # /ws/command (core/api/routers/websocket.py::ws_command_http).
        # classify_intent()/classify_intent_llm() can hand this a task_type
        # that is YELLOW or RED tier (e.g. "code_task" is in
        # PermissionGateway's RED_INTERACTIVE_TOOLS), and Governor.dispatch()'s
        # own Council review for RED-tier types is advisory-only -- a
        # rejection only logs "proceeding with caution" and execution
        # continues. Fixed by routing through the exact same canonical
        # Candidate -> DecisionEngine.evaluate() -> PermissionGateway.execute()
        # pipeline RR-3.6 established, proposed_by="voice" -- this is not a
        # new identity: it is the SAME literal string
        # permission_gateway.py's own RED tier already special-cases
        # ("Typed by the authenticated owner ... or SPOKEN after the wake
        # word on the owner's own machine. The command itself IS the
        # confirmation"), and config.py's own 2026-08-04 RED-tier hardening
        # comment for code_task/code_generate/code_fix/code_debug explicitly
        # anticipates this exact caller: "owner-typed/voice commands still
        # pre-confirm instantly". Correctly meaningful now that this
        # endpoint requires network-level authentication (see voice_ws.py's
        # RR-3.7C fix) -- "voice" was never a safe default identity for an
        # unauthenticated caller, only for one the server has verified.
        try:
            from core.loop.decision_engine import DecisionEngine, Candidate
            from core.loop.permission_gateway import PermissionGateway, Action

            candidate = Candidate(
                action_type=task_type,
                params={"query": text, "user_message": text, "source": "voice_realtime"},
                goal_ids=[],
                urgency=0.7,
                confidence=0.75,
                source="voice_intent",
            )
            decision = await DecisionEngine().evaluate([candidate])
            winner = decision.winner
            gateway_task = asyncio.create_task(PermissionGateway().execute(Action(
                action_type=winner.action_type,
                params=winner.params,
                proposed_by="voice",
            )))
            done, _ = await asyncio.wait({gateway_task}, timeout=_work_ack_delay())
            if not done:
                await self._send_work_ack()
            gateway_result = await gateway_task
            result = gateway_result.result or {}

            if not gateway_result.approved:
                status = "blocked"
                summary = gateway_result.reason or "not authorized"
            elif result.get("status") == "not_implemented":
                status = "not_implemented"
                summary = result.get("note") or f"'{winner.action_type}' is not implemented"
            elif result.get("status") == "ok":
                status = "ok"
                summary = str(
                    result.get("summary")
                    or result.get("message")
                    or f"{task_type.replace('_', ' ')} finished."
                )[:280]
            elif result.get("status") == "no_agents":
                status = "no_agents"
                summary = f"No agent is registered for {task_type.replace('_', ' ')} yet."
            else:
                status = result.get("status", "unknown")
                summary = f"{task_type.replace('_', ' ')} came back with status {status}."

            if not self._closed:
                await self._safe_send({"type": "action_result", "task_type": task_type,
                                       "status": status, "text": summary})
                await self._speak_text(summary)
            self._store_turn(text, summary, ["action", task_type])
        except Exception as e:
            logger.error(f"[VECTOR][realtime] action '{task_type}' failed: {e}")
            if not self._closed:
                await self._speak_text("That task hit an error. Details are in the log.")

    async def _publish_voice_event(self, text: str, task_type: str) -> None:
        """Wake the autonomous loop via the event bus (kills the 10s poll path)."""
        try:
            from core.event_bus.bus import get_event_bus
            from core.event_bus.types import Event, EventType
            bus = await get_event_bus()
            await bus.publish(Event(
                event_type=EventType.VOICE_INPUT,
                data={"text": text, "task_type": task_type},
                source="voice_realtime",
            ))
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] voice event publish skipped: {e}")

    # ── Phase 5: proactive speech ─────────────────────────────────────────────

    def _subscribe_nudges(self) -> None:
        try:
            from core.loop.nudge_engine import nudge_engine
            if hasattr(nudge_engine, "subscribe"):
                self._nudge_unsub = nudge_engine.subscribe(self._on_nudge)
                logger.info("[VECTOR][realtime] proactive speech armed")
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] nudge subscribe skipped: {e}")

    def _on_nudge(self, nudge: dict) -> None:
        """Sync callback from nudge_engine — schedule async speech if allowed."""
        try:
            asyncio.get_running_loop().create_task(self._maybe_speak_nudge(nudge))
        except RuntimeError:
            pass  # no running loop in caller thread — skip

    async def _maybe_speak_nudge(self, nudge: dict) -> None:
        if self._closed or not nudge:
            return
        state = str(self._conv.current_state)
        if state not in ("IDLE", "LISTENING"):
            return                                # never talk over a turn
        priority = float(nudge.get("priority", 0.5))
        if priority < self._proactive_min_priority:
            return
        now = time.localtime()
        if _in_quiet_hours(now.tm_hour * 60 + now.tm_min, self._quiet_hours):
            return
        try:
            from core.loop.presence import allow_proactive
            if not allow_proactive("realtime_voice"):
                return
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass
        text = str(nudge.get("text", "")).strip()
        if not text:
            return
        logger.info("[VECTOR][realtime] proactive: {}", text[:80])
        await self._safe_send({"type": "proactive", "text": text})
        await self._speak_text(text)
        self._store_turn("(proactive)", text, ["proactive", str(nudge.get("rule", ""))])

    # ── plumbing ──────────────────────────────────────────────────────────────

    async def _cancel_speaking(self) -> None:
        self._cancel_speak.set()
        task = self._speak_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._speak_task = None

    async def _state(self, value: str) -> None:
        await self._safe_send({"type": "state", "value": value})
        if self._orb is not None:
            try:
                orb_map = {"LISTENING": "listening", "USER_SPEAKING": "listening",
                           "PROCESSING": "processing", "VECTOR_SPEAKING": "speaking",
                           "IDLE": "idle"}
                await self._orb(orb_map.get(value, "idle"))
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass

    async def _safe_send(self, payload: dict) -> None:
        if self._closed:
            return
        try:
            await self._send(payload)
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] send failed (client gone?): {e}")
            self._closed = True

    def _store_turn(self, user_text: str, vector_text: str, tags: list[str]) -> None:
        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="realtime_conversation",
                content=f"Q: {user_text} | A: {vector_text}",
                tags=["voice"] + tags,
                source="realtime_voice",
            )
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] episodic store skipped: {e}")
