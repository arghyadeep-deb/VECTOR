# SPEC-09: Home Assistant Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Transform VECTOR's home control from 5/100 to 85/100 -- full Home Assistant API integration enabling read/write access to all entities (lights, sensors, climate, switches), natural language voice control, context-aware automations, and an optional ESP32 voice satellite.

**Architecture:** VECTOR connects to a local Home Assistant instance via REST and WebSocket APIs. EntityManager discovers and caches entities. VoiceBridge maps NLU to HA service calls. AutomationEngine triggers context-aware actions. Optional ESP32-S3 for room-level voice.

**Tech Stack:** Home Assistant REST API, Home Assistant WebSocket API, httpx, asyncio, ESP32-S3 (Arduino/ESP-IDF, optional)

**Score:** Current 5/100 -> Target 85/100

---

## 1. Problem Statement

### 1.1 Current Limitations

Home control scores 5/100 across six dimensions:

| Dimension | Score | Issue |
|-----------|-------|-------|
| Integration | 0/100 | Zero Home Assistant integration |
| Voice Control | 0/100 | No home automation intent handler |
| Context Awareness | 0/100 | Cannot act on time/presence data |
| Automation | 0/100 | No trigger conditions or schedules |
| Sensing | 10/100 | Phone node basic detection only |
| Hardware | 5/100 | No smart home control hardware |

### 1.2 Opportunity

Home Assistant is already running on the local network or a Fly.io VM. HA has 2,000+ integrations covering virtually every smart home device. VECTOR simply needs to connect, read entity states, and issue service calls.

### 1.3 Use Cases

| User Says | VECTOR Action |
|-----------|---------------|
| Good morning | Turn on bedroom lights (30%), set thermostat to 22C |
| Turn off the lights | Read all light entities, call light.turn_off |
| What is the temperature outside? | Read weather entity temperature |
| Set living room to 24 degrees | Call climate.set_temperature |
| Is the front door locked? | Read lock entity state |
| Lock up the house | Lock all doors, turn off all lights, arm alarm |
| Movie mode | Dim lights to 10%, close curtains, turn on TV |

---

## 2. Current Architecture

### 2.1 What Exists

No Home Assistant code exists at all. Relevant existing modules:

| Module | Role |
|--------|------|
| core/voice/ambient_listener.py | Voice pipeline |
| core/loop/context_engine.py | Time, user state |
| core/loop/decision_engine.py | Action scoring |
| phone_node/ | Phone sensors |
| core/config.py | Configuration |

### 2.2 Home Assistant API Reference

REST API (port 8123):
  GET    /api/states                              -> all entity states
  GET    /api/states/<entity_id>                  -> single entity state
  POST   /api/services/<domain>/<service>         -> call service
  GET    /api/config                              -> HA configuration
  GET    /api/events                              -> event registry
  GET    /api/services                            -> service registry

WebSocket API (ws://host:8123/api/websocket):
  Authentication -> auth message with token
  subscribe_events -> real-time state changes
  get_states -> cached entity list
  call_service -> execute action

Auth: Long-Lived Access Token

---

## 3. Target Architecture

### 3.1 High-Level Flow

VECTOR connects to a local Home Assistant instance on port 8123. Two API surfaces are used:
REST for initial state sync and service calls, WebSocket for real-time event subscriptions.

HAConnector manages both connections with automatic reconnection.
EntityManager discovers and caches all entities grouped by room/type.
VoiceBridge maps NLU intents from voice pipeline to HA service calls.
AutomationEngine triggers actions based on VECTOR context (time, presence, security).
ESP32 satellite provides always-listening voice in any room.

### 3.2 Component Architecture

HomeIntegrationSystem
+-- HAConnector
|   +-- HAAuth                 -- authentication + token refresh
|   +-- HARestClient           -- REST endpoint wrapper
|   +-- HAWebSocketClient      -- WebSocket event subscription
+-- EntityManager
|   +-- EntityRegistry         -- discovered entities by id/name/area
|   +-- EntityCache            -- TTL-based state cache
|   +-- EntityMatcher          -- fuzzy name matching for voice
+-- VoiceBridge
|   +-- IntentMapper           -- NLU intent -> HA service call
|   +-- EntityResolver         -- resolves entities from NLU phrases
|   +-- ConfirmDialog          -- high-risk action confirmation
+-- AutomationEngine
|   +-- ContextTrigger         -- time + presence + security -> action
|   +-- SceneManager           -- named scenes (good morning, movie mode)
|   +-- Scheduler              -- time-based automation rules
+-- ESP32Firmware (optional)
    +-- AudioCapture            -- I2S microphone streaming
    +-- WakeWordDetector        -- lightweight on-device wake word
    +-- WiFiStreamer            -- audio relay to VECTOR

### 1.2 Opportunity

Home Assistant is already running on the local network or a Fly.io VM. HA has 2,000+ integrations. VECTOR connects, reads entity states, and issues service calls.

### 1.3 Use Cases

| User Says | VECTOR Action |
|-----------|---------------|
| Good morning | Turn on bedroom lights (30%), set thermostat to 22C |
| Turn off the lights | Call light.turn_off for all lights |
| What is the temperature outside? | Read weather entity |
| Set living room to 24 degrees | Call climate.set_temperature |
| Is the front door locked? | Read lock entity state |
| Lock up the house | Lock all doors, turn off lights, arm alarm |
| Movie mode | Dim lights to 10%, close curtains, turn on TV |

---

## 2. Current Architecture

### 2.1 What Exists

No Home Assistant code exists. Relevant existing modules:
- core/voice/ambient_listener.py - voice pipeline
- core/loop/context_engine.py - time, user state
- core/loop/decision_engine.py - action scoring
- phone_node/ - phone sensors
- core/config.py - configuration

### 2.2 Home Assistant API Reference

REST API (port 8123):
  GET /api/states -> all entity states
  GET /api/states/<entity_id> -> single entity state
  POST /api/services/<domain>/<service> -> call service
  GET /api/config -> HA configuration
  GET /api/services -> service registry

WebSocket API (ws://host:8123/api/websocket):
  Authentication -> auth message with token
  subscribe_events -> real-time state changes
  call_service -> execute action

Auth: Long-Lived Access Token from HA profile page

---

## 3. Target Architecture

### 3.1 High-Level Architecture

VECTOR connects to local HA on port 8123. REST for initial sync and calls, WebSocket for subscriptions.
HAConnector manages both connections with auto-reconnect.
EntityManager discovers and caches entities grouped by room/type.
VoiceBridge maps NLU intents to HA service calls.
AutomationEngine triggers actions based on VECTOR context (time, presence, security).
ESP32 satellite provides always-listening voice in any room.

### 3.2 Component Architecture

HomeIntegrationSystem
+-- HAConnector
|   +-- HAAuth - authentication and token refresh
|   +-- HARestClient - REST endpoint wrapper
|   +-- HAWebSocketClient - event subscription
+-- EntityManager
|   +-- EntityRegistry - discovered entities by id/name/area
|   +-- EntityCache - TTL-based state cache (30s)
|   +-- EntityMatcher - fuzzy name matching for voice
+-- VoiceBridge
|   +-- IntentMapper - NLU intent to HA service call
|   +-- EntityResolver - resolves entities from NLU phrases
|   +-- ConfirmDialog - high-risk action confirmation
+-- AutomationEngine
|   +-- ContextTrigger - time + presence + security triggers
|   +-- SceneManager - named scenes (good morning, movie mode)
|   +-- Scheduler - time-based automation rules
+-- ESP32Firmware (optional)
    +-- AudioCapture - I2S microphone streaming
    +-- WakeWordDetector - lightweight on-device wake word
    +-- WiFiStreamer - audio relay to VECTOR over UDP/WebSocket

### 3.3 Data Flow: Voice Command

User: "Hey VECTOR, turn off the living room lights"

1. VECTOR voice pipeline: wake -> ASR -> intent classification
   Intent: {action: turn_off, target: light, area: living_room}

2. VoiceBridge.handle_intent():
   EntityResolver: "living room lights" -> [light.living_room_ceiling, light.living_room_lamp]
   ConfirmDialog: confidence > 0.9 -> execute directly, else ask confirmation
   IntentMapper -> HA service call: light.turn_off

3. HAConnector.call_service('light', 'turn_off', {entity_id: [...]})
   POST /api/services/light/turn_off -> {success: true}

4. VECTOR TTS: 'Living room lights turned off.'
   Entity cache invalidated. WebSocket refreshes state.

Total latency target: <2s from wake word to lights off

### 3.4 Data Flow: Context Automation

Context: 10:15 PM, no movement for 30 minutes, phone charging

1. AutomationEngine.on_tick():
   Context: time=22:15, user_presence=false, stationary_minutes=35
   Rule match: nighttime_auto_off (time+no_movement condition met)

2. Execute 'nighttime_auto_off' scene:
   - light.turn_off all lights
   - climate.set_temperature to 18C
   - lock.lock all locks
   - cover.close_cover all covers

3. Log to emergency log / Pushover notification (optional)

---

## 4. Component Breakdown

### 4.1 HAConnector

File: districts/home_assistant/connector.py (new, ~350 lines)

Responsibility: Async Python client to local HA via REST + WebSocket API.

class HAConfig:
    host: str = 'homeassistant.local'
    port: int = 8123
    access_token: str = ''
    reconnect_delay: float = 5.0
    max_retries: int = 5
    rate_limit_per_second: int = 10

class HAConnector:
    manages REST client (httpx) and WebSocket client
    connect() -> authenticate() -> subscribe_events() -> ready
    call_service(domain, service, data, target) -> dict
    get_states(entity_id=None) -> list[dict]
    on_event(event_type, handler) -> register callback
    auto-reconnect with exponential backoff (max 60s)
    rate limiting via sliding window (10 req/s)

class HARestClient:
    get_states() -> list[dict]
    get_state(entity_id) -> dict
    call_service(domain, service, data) -> list[dict]
    get_config() -> dict
    get_services() -> dict

class HAWebSocketClient:
    connect() -> authenticate -> message_loop
    subscribe_events(event_type=None) -> int (msg_id)
    auth: receive auth_required, send token, receive auth_ok
    event callback dispatch by event_type

### 4.2 EntityManager

File: districts/home_assistant/entity_manager.py (new, ~250 lines)

class HAEntity:
    entity_id, domain, name, state, area, attributes, last_changed

class EntityManager:
    discover: fetch all states from HA on startup
    group by area (living room) and domain (light, sensor, lock)
    cache: in-memory dict with 30s TTL, invalidated on state_changed events
    fuzzy_match(query):
      1. tokenize input, extract area + type keywords
      2. match area: living room, bedroom, kitchen, etc.
      3. match type: light->light/lamp, climate->temperature, etc.
      4. score: area match (weight 3) + type match (weight 2) + name fuzzy (weight 1)
      5. return sorted by score, threshold > 0.6

Types: light, climate, lock, cover, switch, sensor, media_player, fan, vacuum
Areas: living room, bedroom, kitchen, bathroom, hallway, office, dining, garage

### 4.3 VoiceBridge

File: districts/home_assistant/voice_bridge.py (new, ~200 lines)

class VoiceCommand:
    intent_type, target_domain, target_area, target_entity, parameters

class VoiceBridge:
    handle_intent(intent_dict, confidence) -> str
    Intent mapping table:
      turn_on(light) -> light.turn_on
      turn_off(light) -> light.turn_off
      set_temperature(X) -> climate.set_temperature
      query_state(entity) -> read from cache
      lock(lock) -> lock.lock (requires confirmation)
      unlock(lock) -> lock.unlock (requires confirmation)
      close(cover) -> cover.close_cover
      open(cover) -> cover.open_cover
    ConfirmDialog: confidence < 0.7 or high-risk domain -> ask user
    Response: format HA result as natural language TTS string

### 4.4 AutomationEngine

File: districts/home_assistant/automation_engine.py (new, ~200 lines)

class AutomationRule:
    name, enabled, trigger_type (time/presence/security), conditions, scene, cooldown_minutes

class AutomationEngine:
    tick(context: dict) -> list of triggered rule names
    execute_scene(name) -> dict of service call results

Built-in rules:
    1. nighttime_auto_off: 10PM-6AM, no movement >30min -> night_mode scene
    2. morning_wakeup: 7AM-8AM, user present -> morning_mode scene
    3. away_mode: user leaves (no movement >1hr + phone disconnected) -> security mode
    4. arrival_mode: user returns (phone reconnects / motion detected) -> restore lights
    5. movie_mode: voice command -> dim lights, close curtains, turn on media
    6. security_breach: security alert -> full lights, audible alert
    7. going_to_bed: 11PM, bedroom motion -> lock up, night climate

Scenes: named sets of HA service calls executed in sequence
  night_mode: turn off lights, set climate 18C, lock doors, close covers
  morning_mode: turn on lights 30%, set climate 22C

Cooldown: prevents re-triggering within N minutes (configurable per rule)

### 4.5 ESP32 Firmware (Optional, Stretch)

File: districts/home_assistant/esp32/ (new, ~300 lines C++)

Hardware: ESP32-S3 + INMP441 I2S microphone
Capabilities: I2S audio capture 16kHz 16-bit mono, wake word detection, WiFi streaming
Protocol: wake detected -> stream PCM to VECTOR -> VECTOR processes -> response audio back

main.cpp: setup WiFi, I2S, main loop with wake state machine
audio_capture.cpp: I2S configuration, DMA buffer management
wake_word.cpp: keyword spotting (energy-based or TFLite Micro)
wifi_streamer.cpp: UDP audio relay to VECTOR endpoint
audio_output.cpp: I2S speaker output for response playback (optional)

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: HA Connector + Entity Manager

Scope: connector.py, entity_manager.py, __init__.py, tests
Deliverables:
- HAConnector with REST + WebSocket + auth + rate limiting + reconnect
- HARestClient wrapping HA REST endpoints
- HAWebSocketClient with event subscription and callbacks
- EntityManager with full discovery, TTL cache, fuzzy matching
- Tests: call_service, get_states, entity matching accuracy

### 5.2 Agent B: Voice Bridge + Automation Engine

Scope: voice_bridge.py, automation_engine.py, scenes.json, integration tests
Deliverables:
- VoiceBridge with full intent-to-service mapping
- EntityResolver via fuzzy matching
- ConfirmDialog with risk detection
- AutomationEngine with 7+ built-in rules
- Scene system for multi-action sequences
- Voice pipeline integration (new intent type: home_control)
- Context engine integration for time/presence triggers

### 5.3 Agent C: ESP32 Firmware (Optional)

Scope: esp32/ directory with platformio.ini and C++ sources
Deliverables:
- I2S microphone capture at 16kHz 16-bit
- WiFi UDP/WebSocket audio streaming
- On-device wake word detection
- Audio response playback via I2S (optional)
- Integration test end-to-end

---

## 6. Implementation Steps

### 6.1 Phase 1: Connection Layer (Agent A)

Step 1.1: Create package structure
- [ ] Create districts/home_assistant/__init__.py

Step 1.2: Implement HAConnector
- [ ] HAConfig dataclass with host, port, token, retry settings
- [ ] httpx.AsyncClient with auth header
- [ ] call_service() for all HA domains (light, climate, lock, etc.)
- [ ] get_states() with optional entity_id filter
- [ ] Rate limiting: sliding window, 10 req/s
- [ ] Error handling: retry on 5xx, log on 4xx

Step 1.3: Implement HAWebSocketClient
- [ ] Connect + authenticate + message_loop
- [ ] Event callback dispatch
- [ ] Auto-reconnect with exponential backoff
- [ ] Graceful shutdown

Step 1.4: Implement EntityManager
- [ ] HAEntity dataclass
- [ ] Initial discovery via get_states()
- [ ] Entity cache with 30s TTL
- [ ] Fuzzy matching: area + type + name scoring
- [ ] Cache invalidation on state_changed

Step 1.5: Test
- [ ] test_connector.py - call_service, get_states, rate limiting
- [ ] test_entity_manager.py - discovery, cache, fuzzy matching

### 6.2 Phase 2: Intelligence Layer (Agent B)

Step 2.1: Implement VoiceBridge
- [ ] VoiceCommand dataclass
- [ ] Intent parsing from voice pipeline NLU output
- [ ] EntityResolver via fuzzy matching
- [ ] ConfirmDialog for high-risk actions
- [ ] Response formatting (HA result -> natural language)

Step 2.2: Wire voice integration
- [ ] Connect VoiceBridge to voice pipeline intent output
- [ ] Add home_control intent type to classifier
- [ ] Test end-to-end: voice -> HA action

Step 2.3: Implement AutomationEngine
- [ ] AutomationRule and Scene dataclasses
- [ ] 7+ built-in rules
- [ ] Scene system
- [ ] Context evaluation and cooldown
- [ ] Pushover notification on triggers

Step 2.4: Test
- [ ] test_voice_bridge.py - intent handling, confirmation
- [ ] test_automation_engine.py - rule matching, scenes, cooldown

### 6.3 Phase 3: ESP32 Satellite (Agent C, Optional)

Step 3.1: Set up ESP32 project
- [ ] Create esp32/ directory and platformio.ini
- [ ] Install Arduino, WiFi, I2S libraries

Step 3.2: Implement audio capture + wake word + streaming
- [ ] I2S capture at 16kHz 16-bit
- [ ] Wake word state machine
- [ ] UDP audio streaming to VECTOR

Step 3.3: Test
- [ ] Audio capture buffer test
- [ ] End-to-end: ESP32 -> VECTOR -> HA action

---

## 7. Files to Create/Modify

Create:
- districts/home_assistant/__init__.py (10 lines)
- districts/home_assistant/connector.py (350 lines)
- districts/home_assistant/entity_manager.py (250 lines)
- districts/home_assistant/voice_bridge.py (200 lines)
- districts/home_assistant/automation_engine.py (200 lines)
- districts/home_assistant/scenes.json (50 lines)
- districts/home_assistant/esp32/platformio.ini (30 lines)
- districts/home_assistant/esp32/main.cpp (80 lines)
- districts/home_assistant/esp32/audio_capture.cpp (100 lines)
- districts/home_assistant/esp32/wake_word.cpp (80 lines)
- districts/home_assistant/esp32/wifi_streamer.cpp (100 lines)
- districts/home_assistant/esp32/audio_output.cpp (80 lines)
- tests/home_assistant/test_connector.py (120 lines)
- tests/home_assistant/test_entity_manager.py (100 lines)
- tests/home_assistant/test_voice_bridge.py (80 lines)
- tests/home_assistant/test_automation_engine.py (80 lines)

Modify:
- core/voice/ambient_listener.py: add home_control intent type
- core/loop/context_engine.py: expose time/presence context
- core/config.py: add HAConfig section
- run_vector.py: add home integration startup option

---

## 8. Success Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Voice -> HA action latency | <2s | Time from wake word to light change |
| Entity discovery count | All HA entities | Compare with HA states endpoint |
| Entity cache hit rate | >90% | Cache hit/miss after 1h |
| Fuzzy match accuracy | >85% | 50 test queries, correct match rate |
| Automation trigger latency | <5s | Context change to HA action |
| HAConnector uptime | >99% | WebSocket reconnect count over 7 days |
| Rate limit compliance | 100% | No 429 responses from HA |
| Confirmation accuracy | >90% | Confirm high-risk, skip low-risk |

Functional:
- VECTOR reads all HA entities on startup
- Voice command executes within 2 seconds
- Automation triggers correctly at 10PM with no movement
- High-risk actions (unlock) prompt confirmation
- Entity cache invalidates within 1s of state change
- HA connection recovers within 30s of restart

Safety:
- No destructive actions without confirmation
- Cooldown prevents rapid re-triggering
- Token stored in config only, never in logs
- Rate limiting prevents HA API abuse

---

## 9. Dependencies

External:
- httpx (already in requirements.txt)
- websockets>=12.0 (add to requirements.txt)

Infrastructure:
- Home Assistant instance running (local LAN or Fly.io VM)
- Long-Lived Access Token from HA profile
- ESP32-S3 + INMP441 microphone (optional, for satellite)

Internal:
- specs-01 voice pipeline (VoiceBridge needs NLU output)
- specs-02 event bus (AutomationEngine publishes events after bus available)
- core/loop/context_engine.py (time/presence/security context)

Config:
- HAConfig.host (default: homeassistant.local)
- HAConfig.port (default: 8123)
- HAConfig.access_token (long-lived token)
- HAConfig.entity_cache_ttl_seconds (default: 30)
- HAConfig.automation_enabled (default: true)
- HAConfig.voice_control_enabled (default: true)
- HAConfig.confirm_high_risk (default: true)

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| HA unreachable (network down) | Medium | High | Cache last states; backoff retry |
| Voice intent misclassification | Medium | High | ConfirmDialog for high-risk actions |
| WebSocket disconnects/missed events | Medium | Medium | Full state sync on reconnect |
| Rate limit exceeded | Low | Low | Sliding window; batch calls |
| Automation rule wrong trigger | Medium | Medium | Cooldown; log all triggers; manual override |
| Token compromised/expired | Low | Critical | Config-only storage; periodic rotation |
| ESP32 audio quality poor | Medium | Medium | Test mics; add noise filtering |

---

## 11. Appendix: HA Service Call Reference

Light domain: turn_on, turn_off, toggle
Climate domain: set_temperature, set_hvac_mode
Lock domain: lock, unlock (high-risk)
Cover domain: open_cover, close_cover, stop_cover, set_cover_position
Switch domain: turn_on, turn_off, toggle
Media player: turn_on, turn_off, volume_set, select_source, play_media

All calls go through HAConnector.call_service(domain, service, data)