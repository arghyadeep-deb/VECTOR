# VectorCode API Reference

Auto-generated from source. Lists every public module, class, and function.

**Generated:** by `scripts/gen_api_docs.py`

---

## Table of Contents

- [acp](#acp)
- [acp_adapter](#acp_adapter)
- [agent](#agent)
- [(root)](#(root))
- [agents](#agents)
- [api](#api)
- [(root)](#(root))
- [(root)](#(root))
- [cli](#cli)
- [(root)](#(root))
- [(root)](#(root))
- [comms](#comms)
- [config](#config)
- [(root)](#(root))
- [context](#context)
- [(root)](#(root))
- [(root)](#(root))
- [cron](#cron)
- [display](#display)
- [engine](#engine)
- [(root)](#(root))
- [gateway](#gateway)
- [(root)](#(root))
- [hooks](#hooks)
- [(root)](#(root))
- [(root)](#(root))
- [mcp](#mcp)
- [mcp_client](#mcp_client)
- [(root)](#(root))
- [memory](#memory)
- [(root)](#(root))
- [migrations](#migrations)
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))
- [persona](#persona)
- [plugins](#plugins)
- [providers](#providers)
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))
- [scripts](#scripts)
- [security](#security)
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))
- [tools](#tools)
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))
- [transports](#transports)
- [utils](#utils)
- [(root)](#(root))
- [vector_cli](#vector_cli)
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))
- [(root)](#(root))

---

## acp

### `acp/server.py`

_ACP server — expose VectorCode as an ACP-compatible agent._

**Classes:**

- **`ACPMessage`**
- **`ACPSession`**
- **`ACPServer`** — Exposes VectorCode as an ACP agent via FastAPI HTTP endpoints.
  - `__init__(self, host: str, port: int) -> None`
  - `build_app(self)`
  - `start(self) -> None`

**Functions:**

- `get_acp_server(port: int) -> 'ACPServer'` — Return the module-level ACPServer singleton, creating it on first call.


---

## acp_adapter

### `acp_adapter/__main__.py`

_Allow running the ACP adapter as ``python -m acp_adapter``._

### `acp_adapter/auth.py`

_ACP auth helpers — detect the currently configured VectorCode provider._

**Functions:**

- `detect_provider() -> Optional[str]` — Resolve the active VectorCode runtime provider, or None if unavailable.
- `has_provider() -> bool` — Return True if VectorCode can resolve any runtime provider credentials.

### `acp_adapter/entry.py`

_CLI entry point for the vectorcode ACP adapter._

**Functions:**

- `main() -> None` — Entry point: load env, configure logging, run the ACP agent.

### `acp_adapter/events.py`

_Callback factories for bridging AIAgent events to ACP notifications._

**Functions:**

- `make_tool_progress_cb(conn: acp.Client, session_id: str, loop: asyncio.AbstractEventLoop, tool_call_ids: Dict[str, Deque[str]], tool_call_meta: Dict[str, Dict[str, Any]]) -> Callable` — Create a ``tool_progress_callback`` for AIAgent.
- `make_thinking_cb(conn: acp.Client, session_id: str, loop: asyncio.AbstractEventLoop) -> Callable` — Create a ``thinking_callback`` for AIAgent.
- `make_step_cb(conn: acp.Client, session_id: str, loop: asyncio.AbstractEventLoop, tool_call_ids: Dict[str, Deque[str]], tool_call_meta: Dict[str, Dict[str, Any]]) -> Callable` — Create a ``step_callback`` for AIAgent.
- `make_message_cb(conn: acp.Client, session_id: str, loop: asyncio.AbstractEventLoop) -> Callable` — Create a callback that streams agent response text to the editor.

### `acp_adapter/permissions.py`

_ACP permission bridging — maps ACP approval requests to vector approval callbacks._

**Functions:**

- `make_approval_callback(request_permission_fn: Callable, loop: asyncio.AbstractEventLoop, session_id: str, timeout: float) -> Callable[[str, str], str]` — Return a vector-compatible ``approval_callback(command, description) -> str``

### `acp_adapter/server.py`

_ACP agent server — exposes VectorCode via the Agent Client Protocol._

**Classes:**

- **`VectorCodeACPAgent`** — ACP Agent implementation wrapping VectorCode AIAgent.
  - `__init__(self, session_manager: SessionManager | None)`
  - `on_connect(self, conn: acp.Client) -> None`
  - `initialize(self, protocol_version: int | None, client_capabilities: ClientCapabilities | None, client_info: Implementation | None) -> InitializeResponse`
  - `authenticate(self, method_id: str) -> AuthenticateResponse | None`
  - `new_session(self, cwd: str, mcp_servers: list | None) -> NewSessionResponse`
  - `load_session(self, cwd: str, session_id: str, mcp_servers: list | None) -> LoadSessionResponse | None`
  - `resume_session(self, cwd: str, session_id: str, mcp_servers: list | None) -> ResumeSessionResponse`
  - `cancel(self, session_id: str) -> None`
  - _(+6 more methods)_

### `acp_adapter/session.py`

_ACP session manager — maps ACP sessions to VectorCode AIAgent instances._

**Classes:**

- **`SessionState`** — Tracks per-session state for an ACP-managed VectorCode agent.
- **`SessionManager`** — Thread-safe manager for ACP sessions backed by VectorCode AIAgent instances.
  - `__init__(self, agent_factory, db)`
  - `create_session(self, cwd: str) -> SessionState`
  - `get_session(self, session_id: str) -> Optional[SessionState]`
  - `remove_session(self, session_id: str) -> bool`
  - `fork_session(self, session_id: str, cwd: str) -> Optional[SessionState]`
  - `list_sessions(self, cwd: str | None) -> List[Dict[str, Any]]`
  - `update_cwd(self, session_id: str, cwd: str) -> Optional[SessionState]`
  - `cleanup(self) -> None`
  - _(+1 more methods)_

### `acp_adapter/tools.py`

_ACP tool-call helpers for mapping vector tools to ACP ToolKind and building content._

**Functions:**

- `get_tool_kind(tool_name: str) -> ToolKind` — Return the ACP ToolKind for a vector tool, defaulting to 'other'.
- `make_tool_call_id() -> str` — Generate a unique tool call ID.
- `build_tool_title(tool_name: str, args: Dict[str, Any]) -> str` — Build a human-readable title for a tool call.
- `build_tool_start(tool_call_id: str, tool_name: str, arguments: Dict[str, Any]) -> ToolCallStart` — Create a ToolCallStart event for the given vector tool invocation.
- `build_tool_complete(tool_call_id: str, tool_name: str, result: Optional[str], function_args: Optional[Dict[str, Any]], snapshot: Any) -> ToolCallProgress` — Create a ToolCallUpdate (progress) event for a completed tool call.
- `extract_locations(arguments: Dict[str, Any]) -> List[ToolCallLocation]` — Extract file-system locations from tool arguments.


---

## agent

### `agent/account_usage.py`

**Classes:**

- **`AccountUsageWindow`**
- **`AccountUsageSnapshot`**
  - `available(self) -> bool`

**Functions:**

- `render_account_usage_lines(snapshot: Optional[AccountUsageSnapshot], markdown: bool) -> list[str]`
- `fetch_account_usage(provider: Optional[str], base_url: Optional[str], api_key: Optional[str]) -> Optional[AccountUsageSnapshot]`

### `agent/anthropic_adapter.py`

_Anthropic Messages API adapter for VectorCode._

**Functions:**

- `build_anthropic_client(api_key: str, base_url: str, timeout: float)` — Create an Anthropic client, auto-detecting setup-tokens vs API keys.
- `build_anthropic_bedrock_client(region: str)` — Create an AnthropicBedrock client for Bedrock Claude models.
- `read_claude_code_credentials() -> Optional[Dict[str, Any]]` — Read refreshable Claude Code OAuth credentials.
- `read_claude_managed_key() -> Optional[str]` — Read Claude's native managed key from ~/.claude.json for diagnostics only.
- `is_claude_code_token_valid(creds: Dict[str, Any]) -> bool` — Check if Claude Code credentials have a non-expired access token.
- `refresh_anthropic_oauth_pure(refresh_token: str, use_json: bool) -> Dict[str, Any]` — Refresh an Anthropic OAuth token without mutating local credential files.
- `resolve_anthropic_token() -> Optional[str]` — Resolve an Anthropic token from all available sources.
- `run_oauth_setup_token() -> Optional[str]` — Run 'claude setup-token' interactively and return the resulting token.
- `run_vector_oauth_login_pure() -> Optional[Dict[str, Any]]` — Run VectorCode-native OAuth PKCE flow and return credential state.
- `read_vector_oauth_credentials() -> Optional[Dict[str, Any]]` — Read VectorCode-managed OAuth credentials from ~/.vectorcode/.anthropic_oauth.json.
- `normalize_model_name(model: str, preserve_dots: bool) -> str` — Normalize a model name for the Anthropic API.
- `convert_tools_to_anthropic(tools: List[Dict]) -> List[Dict]` — Convert OpenAI tool definitions to Anthropic format.
- `convert_messages_to_anthropic(messages: List[Dict], base_url: str | None) -> Tuple[Optional[Any], List[Dict]]` — Convert OpenAI-format messages to Anthropic format.
- `build_anthropic_kwargs(model: str, messages: List[Dict], tools: Optional[List[Dict]], max_tokens: Optional[int], reasoning_config: Optional[Dict[str, Any]], tool_choice: Optional[str], is_oauth: bool, preserve_dots: bool, context_length: Optional[int], base_url: str | None, fast_mode: bool) -> Dict[str, Any]` — Build kwargs for anthropic.messages.create().

### `agent/auxiliary_client.py`

_Shared auxiliary client router for side tasks._

**Classes:**

- **`CodexAuxiliaryClient`** — OpenAI-client-compatible wrapper that routes through Codex Responses API.
  - `__init__(self, real_client: OpenAI, model: str)`
  - `close(self)`
- **`AsyncCodexAuxiliaryClient`** — Async-compatible wrapper matching AsyncOpenAI.chat.completions.create().
  - `__init__(self, sync_wrapper: 'CodexAuxiliaryClient')`
- **`AnthropicAuxiliaryClient`** — OpenAI-client-compatible wrapper over a native Anthropic client.
  - `__init__(self, real_client: Any, model: str, api_key: str, base_url: str, is_oauth: bool)`
  - `close(self)`
- **`AsyncAnthropicAuxiliaryClient`**
  - `__init__(self, sync_wrapper: 'AnthropicAuxiliaryClient')`

**Functions:**

- `resolve_provider_client(provider: str, model: str, async_mode: bool, raw_codex: bool, explicit_base_url: str, explicit_api_key: str, api_mode: str, main_runtime: Optional[Dict[str, Any]], is_vision: bool) -> Tuple[Optional[Any], Optional[str]]` — Central router: given a provider name and optional model, return a
- `get_text_auxiliary_client(task: str, main_runtime: Optional[Dict[str, Any]]) -> Tuple[Optional[OpenAI], Optional[str]]` — Return (client, default_model_slug) for text-only auxiliary tasks.
- `get_async_text_auxiliary_client(task: str, main_runtime: Optional[Dict[str, Any]])` — Return (async_client, model_slug) for async consumers.
- `get_available_vision_backends() -> List[str]` — Return the currently available vision backends in auto-selection order.
- `resolve_vision_provider_client(provider: Optional[str], model: Optional[str], base_url: Optional[str], api_key: Optional[str], async_mode: bool) -> Tuple[Optional[str], Optional[Any], Optional[str]]` — Resolve the client actually used for vision tasks.
- `get_auxiliary_extra_body() -> dict` — Return extra_body kwargs for auxiliary API calls.
- `auxiliary_max_tokens_param(value: int) -> dict` — Return the correct max tokens kwarg for the auxiliary client's provider.
- `neuter_async_httpx_del() -> None` — Monkey-patch ``AsyncHttpxClientWrapper.__del__`` to be a no-op.
- `shutdown_cached_clients() -> None` — Close all cached clients (sync and async) to prevent event-loop errors.
- `cleanup_stale_async_clients() -> None` — Force-close cached async clients whose event loop is closed.
- `call_llm(task: str, provider: str, model: str, base_url: str, api_key: str, main_runtime: Optional[Dict[str, Any]], messages: list, temperature: float, max_tokens: int, tools: list, timeout: float, extra_body: dict) -> Any` — Centralized synchronous LLM call.
- `extract_content_or_reasoning(response) -> str` — Extract content from an LLM response, falling back to reasoning fields.
- `async_call_llm(task: str, provider: str, model: str, base_url: str, api_key: str, messages: list, temperature: float, max_tokens: int, tools: list, timeout: float, extra_body: dict) -> Any` — Centralized asynchronous LLM call.

### `agent/bedrock_adapter.py`

_AWS Bedrock Converse API adapter for VectorCode._

**Functions:**

- `reset_client_cache()` — Clear cached boto3 clients. Used in tests and profile switches.
- `invalidate_runtime_client(region: str) -> bool` — Evict the cached ``bedrock-runtime`` client for a single region.
- `is_stale_connection_error(exc: BaseException) -> bool` — Return True if ``exc`` indicates a dead/stale Bedrock HTTP connection.
- `resolve_aws_auth_env_var(env: Optional[Dict[str, str]]) -> Optional[str]` — Return the name of the AWS auth source that is active, or None.
- `has_aws_credentials(env: Optional[Dict[str, str]]) -> bool` — Return True if any AWS credential source is detected.
- `resolve_bedrock_region(env: Optional[Dict[str, str]]) -> str` — Resolve the AWS region for Bedrock API calls.
- `is_anthropic_bedrock_model(model_id: str) -> bool` — Return True if the model is an Anthropic Claude model on Bedrock.
- `convert_tools_to_converse(tools: List[Dict]) -> List[Dict]` — Convert OpenAI-format tool definitions to Bedrock Converse ``toolConfig``.
- `convert_messages_to_converse(messages: List[Dict]) -> Tuple[Optional[List[Dict]], List[Dict]]` — Convert OpenAI-format messages to Bedrock Converse format.
- `normalize_converse_response(response: Dict) -> SimpleNamespace` — Convert a Bedrock Converse API response to an OpenAI-compatible object.
- `normalize_converse_stream_events(event_stream) -> SimpleNamespace` — Consume a Bedrock ConverseStream event stream and build an OpenAI-compatible response.
- `stream_converse_with_callbacks(event_stream, on_text_delta, on_tool_start, on_reasoning_delta, on_interrupt_check) -> SimpleNamespace` — Process a Bedrock ConverseStream event stream with real-time callbacks.
- `build_converse_kwargs(model: str, messages: List[Dict], tools: Optional[List[Dict]], max_tokens: int, temperature: Optional[float], top_p: Optional[float], stop_sequences: Optional[List[str]], guardrail_config: Optional[Dict]) -> Dict[str, Any]` — Build kwargs for ``bedrock-runtime.converse()`` or ``converse_stream()``.
- `call_converse(region: str, model: str, messages: List[Dict], tools: Optional[List[Dict]], max_tokens: int, temperature: Optional[float], top_p: Optional[float], stop_sequences: Optional[List[str]], guardrail_config: Optional[Dict]) -> SimpleNamespace` — Call Bedrock Converse API (non-streaming) and return an OpenAI-compatible response.
- `call_converse_stream(region: str, model: str, messages: List[Dict], tools: Optional[List[Dict]], max_tokens: int, temperature: Optional[float], top_p: Optional[float], stop_sequences: Optional[List[str]], guardrail_config: Optional[Dict]) -> SimpleNamespace` — Call Bedrock ConverseStream API and return an OpenAI-compatible response.
- _(+6 more functions)_

### `agent/codex_responses_adapter.py`

_Codex Responses API adapter._

### `agent/context_compressor.py`

_Automatic context window compression for long conversations._

**Classes:**

- **`ContextCompressor`** — Default context engine — compresses conversation context via lossy summarization.
  - `name(self) -> str`
  - `on_session_reset(self) -> None`
  - `update_model(self, model: str, context_length: int, base_url: str, api_key: str, provider: str, api_mode: str) -> None`
  - `__init__(self, model: str, threshold_percent: float, protect_first_n: int, protect_last_n: int, summary_target_ratio: float, quiet_mode: bool, summary_model_override: str, base_url: str, api_key: str, config_context_length: int | None, provider: str, api_mode: str)`
  - `update_from_response(self, usage: Dict[str, Any])`
  - `should_compress(self, prompt_tokens: int) -> bool`
  - `has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool`
  - `compress(self, messages: List[Dict[str, Any]], current_tokens: int, focus_topic: str) -> List[Dict[str, Any]]`

### `agent/context_engine.py`

_Abstract base class for pluggable context engines._

**Classes:**

- **`ContextEngine`** — Base class all context engines must implement.
  - `name(self) -> str`
  - `update_from_response(self, usage: Dict[str, Any]) -> None`
  - `should_compress(self, prompt_tokens: int) -> bool`
  - `compress(self, messages: List[Dict[str, Any]], current_tokens: int, focus_topic: str) -> List[Dict[str, Any]]`
  - `should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool`
  - `has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool`
  - `on_session_start(self, session_id: str) -> None`
  - `on_session_end(self, session_id: str, messages: List[Dict[str, Any]]) -> None`
  - _(+5 more methods)_

### `agent/context_references.py`

**Classes:**

- **`ContextReference`**
- **`ContextReferenceResult`**

**Functions:**

- `parse_context_references(message: str) -> list[ContextReference]`
- `preprocess_context_references(message: str, cwd: str | Path, context_length: int, url_fetcher: Callable[[str], str | Awaitable[str]] | None, allowed_root: str | Path | None) -> ContextReferenceResult`
- `preprocess_context_references_async(message: str, cwd: str | Path, context_length: int, url_fetcher: Callable[[str], str | Awaitable[str]] | None, allowed_root: str | Path | None) -> ContextReferenceResult`

### `agent/copilot_acp_client.py`

_OpenAI-compatible shim that forwards VectorCode requests to `copilot --acp`._

**Classes:**

- **`CopilotACPClient`** — Minimal OpenAI-client-compatible facade for Copilot ACP.
  - `__init__(self, api_key: str | None, base_url: str | None, default_headers: dict[str, str] | None, acp_command: str | None, acp_args: list[str] | None, acp_cwd: str | None, command: str | None, args: list[str] | None)`
  - `close(self) -> None`

### `agent/credential_pool.py`

_Persistent multi-credential pool for same-provider failover._

**Classes:**

- **`PooledCredential`**
  - `from_dict(cls, provider: str, payload: Dict[str, Any]) -> 'PooledCredential'`
  - `to_dict(self) -> Dict[str, Any]`
  - `runtime_api_key(self) -> str`
  - `runtime_base_url(self) -> Optional[str]`
- **`CredentialPool`**
  - `__init__(self, provider: str, entries: List[PooledCredential])`
  - `has_credentials(self) -> bool`
  - `has_available(self) -> bool`
  - `entries(self) -> List[PooledCredential]`
  - `current(self) -> Optional[PooledCredential]`
  - `select(self) -> Optional[PooledCredential]`
  - `peek(self) -> Optional[PooledCredential]`
  - `mark_exhausted_and_rotate(self, status_code: Optional[int], error_context: Optional[Dict[str, Any]]) -> Optional[PooledCredential]`
  - _(+7 more methods)_

**Functions:**

- `label_from_token(token: str, fallback: str) -> str`
- `get_custom_provider_pool_key(base_url: str) -> Optional[str]` — Look up the custom_providers list in config.yaml and return 'custom:<name>' for a matching base_url.
- `list_custom_pool_providers() -> List[str]` — Return all 'custom:*' pool keys that have entries in auth.json.
- `get_pool_strategy(provider: str) -> str` — Return the configured selection strategy for a provider.
- `load_pool(provider: str) -> CredentialPool`

### `agent/credential_sources.py`

_Unified removal contract for every credential source VectorCode reads from._

**Classes:**

- **`RemovalResult`** — Outcome of removing a credential source.
- **`RemovalStep`** — How to remove one specific credential source cleanly.
  - `matches(self, provider: str, source: str) -> bool`

**Functions:**

- `register(step: RemovalStep) -> RemovalStep`
- `find_removal_step(provider: str, source: str) -> Optional[RemovalStep]` — Return the first matching RemovalStep, or None if unregistered.

### `agent/display.py`

_CLI presentation -- spinner, kawaii faces, tool preview formatting._

**Classes:**

- **`LocalEditSnapshot`** — Pre-tool filesystem snapshot used to render diffs locally after writes.
- **`KawaiiSpinner`** — Animated spinner with kawaii faces for CLI feedback during tool execution.
  - `get_waiting_faces(cls) -> list`
  - `get_thinking_faces(cls) -> list`
  - `get_thinking_verbs(cls) -> list`
  - `__init__(self, message: str, spinner_type: str, print_fn)`
  - `start(self)`
  - `update_text(self, new_message: str)`
  - `print_above(self, text: str)`
  - `stop(self, final_message: str)`

**Functions:**

- `set_tool_preview_max_len(n: int) -> None` — Set the global max length for tool call previews. 0 = no limit.
- `get_tool_preview_max_len() -> int` — Return the configured max preview length (0 = unlimited).
- `get_skin_tool_prefix() -> str` — Get tool output prefix character from active skin.
- `get_tool_emoji(tool_name: str, default: str) -> str` — Get the display emoji for a tool.
- `build_tool_preview(tool_name: str, args: dict, max_len: int | None) -> str | None` — Build a short preview of a tool call's primary argument for display.
- `capture_local_edit_snapshot(tool_name: str, function_args: dict | None) -> LocalEditSnapshot | None` — Capture before-state for local write previews.
- `extract_edit_diff(tool_name: str, result: str | None, function_args: dict | None, snapshot: LocalEditSnapshot | None) -> str | None` — Extract a unified diff from a file-edit tool result.
- `render_edit_diff_with_delta(tool_name: str, result: str | None, function_args: dict | None, snapshot: LocalEditSnapshot | None, print_fn) -> bool` — Render an edit diff inline without taking over the terminal UI.
- `get_cute_tool_message(tool_name: str, args: dict, duration: float, result: str | None) -> str` — Generate a formatted tool completion line for CLI quiet mode.

### `agent/error_classifier.py`

_API error classification for smart failover and recovery._

**Classes:**

- **`FailoverReason`** — Why an API call failed — determines recovery strategy.
- **`ClassifiedError`** — Structured classification of an API error with recovery hints.
  - `is_auth(self) -> bool`

**Functions:**

- `classify_api_error(error: Exception, provider: str, model: str, approx_tokens: int, context_length: int, num_messages: int) -> ClassifiedError` — Classify an API error into a structured recovery recommendation.

### `agent/file_safety.py`

_Shared file safety rules used by both tools and ACP shims._

**Functions:**

- `build_write_denied_paths(home: str) -> set[str]` — Return exact sensitive paths that must never be written.
- `build_write_denied_prefixes(home: str) -> list[str]` — Return sensitive directory prefixes that must never be written.
- `get_safe_write_root() -> Optional[str]` — Return the resolved VECTOR_WRITE_SAFE_ROOT path, or None if unset.
- `is_write_denied(path: str) -> bool` — Return True if path is blocked by the write denylist or safe root.
- `get_read_block_error(path: str) -> Optional[str]` — Return an error message when a read targets internal VectorCode cache files.

### `agent/gemini_cloudcode_adapter.py`

_OpenAI-compatible facade that talks to Google's Cloud Code Assist backend._

**Classes:**

- **`GeminiCloudCodeClient`** — Minimal OpenAI-SDK-compatible facade over Code Assist v1internal.
  - `__init__(self, api_key: Optional[str], base_url: Optional[str], default_headers: Optional[Dict[str, str]], project_id: str)`
  - `close(self) -> None`

**Functions:**

- `build_gemini_request(messages: List[Dict[str, Any]], tools: Any, tool_choice: Any, temperature: Optional[float], max_tokens: Optional[int], top_p: Optional[float], stop: Any, thinking_config: Any) -> Dict[str, Any]` — Build the inner Gemini request body (goes inside ``request`` wrapper).
- `wrap_code_assist_request(project_id: str, model: str, inner_request: Dict[str, Any], user_prompt_id: Optional[str]) -> Dict[str, Any]` — Wrap the inner Gemini request in the Code Assist envelope.

### `agent/gemini_native_adapter.py`

_OpenAI-compatible facade over Google AI Studio's native Gemini API._

**Classes:**

- **`GeminiAPIError`** — Error shape compatible with VectorCode retry/error classification.
  - `__init__(self, message: str, code: str, status_code: Optional[int], response: Optional[httpx.Response], retry_after: Optional[float], details: Optional[Dict[str, Any]]) -> None`
- **`GeminiNativeClient`** — Minimal OpenAI-SDK-compatible facade over Gemini's native REST API.
  - `__init__(self, api_key: str, base_url: Optional[str], default_headers: Optional[Dict[str, str]], timeout: Any, http_client: Optional[httpx.Client]) -> None`
  - `close(self) -> None`
- **`AsyncGeminiNativeClient`** — Async wrapper used by auxiliary_client for native Gemini calls.
  - `__init__(self, sync_client: GeminiNativeClient)`
  - `close(self) -> None`

**Functions:**

- `is_native_gemini_base_url(base_url: str) -> bool` — Return True when the endpoint speaks Gemini's native REST API.
- `probe_gemini_tier(api_key: str, base_url: str, model: str, timeout: float) -> str` — Probe a Google AI Studio API key and return its tier.
- `is_free_tier_quota_error(error_message: str) -> bool` — Return True when a Gemini 429 message indicates free-tier exhaustion.
- `build_gemini_request(messages: List[Dict[str, Any]], tools: Any, tool_choice: Any, temperature: Optional[float], max_tokens: Optional[int], top_p: Optional[float], stop: Any, thinking_config: Any) -> Dict[str, Any]`
- `translate_gemini_response(resp: Dict[str, Any], model: str) -> SimpleNamespace`
- `translate_stream_event(event: Dict[str, Any], model: str, tool_call_indices: Dict[str, Dict[str, Any]]) -> List[_GeminiStreamChunk]`
- `gemini_http_error(response: httpx.Response) -> GeminiAPIError`

### `agent/gemini_schema.py`

_Helpers for translating OpenAI-style tool schemas to Gemini's schema subset._

**Functions:**

- `sanitize_gemini_schema(schema: Any) -> Dict[str, Any]` — Return a Gemini-compatible copy of a tool parameter schema.
- `sanitize_gemini_tool_parameters(parameters: Any) -> Dict[str, Any]` — Normalize tool parameters to a valid Gemini object schema.

### `agent/google_code_assist.py`

_Google Code Assist API client — project discovery, onboarding, quota._

**Classes:**

- **`CodeAssistError`** — Exception raised by the Code Assist (``cloudcode-pa``) integration.
  - `__init__(self, message: str, code: str, status_code: Optional[int], response: Any, retry_after: Optional[float], details: Optional[Dict[str, Any]]) -> None`
- **`ProjectIdRequiredError`**
  - `__init__(self, message: str) -> None`
- **`CodeAssistProjectInfo`** — Result from ``load_code_assist``.
- **`QuotaBucket`**
- **`ProjectContext`** — Resolved state for a given OAuth session.

**Functions:**

- `load_code_assist(access_token: str, project_id: str, user_agent_model: str) -> CodeAssistProjectInfo` — Call ``POST /v1internal:loadCodeAssist`` with prod → sandbox fallback.
- `onboard_user(access_token: str, tier_id: str, project_id: str, user_agent_model: str) -> Dict[str, Any]` — Call ``POST /v1internal:onboardUser`` to provision the user.
- `retrieve_user_quota(access_token: str, project_id: str, user_agent_model: str) -> List[QuotaBucket]` — Call ``POST /v1internal:retrieveUserQuota`` and parse ``buckets[]``.
- `resolve_project_context(access_token: str, configured_project_id: str, env_project_id: str, user_agent_model: str) -> ProjectContext` — Figure out what project id + tier to use for requests.

### `agent/google_oauth.py`

_Google OAuth PKCE flow for the Gemini (google-gemini-cli) inference provider._

**Classes:**

- **`GoogleOAuthError`** — Raised for any failure in the Google OAuth flow.
  - `__init__(self, message: str, code: str) -> None`
- **`RefreshParts`**
  - `parse(cls, packed: str) -> 'RefreshParts'`
  - `format(self) -> str`
- **`GoogleCredentials`**
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'GoogleCredentials'`
  - `expires_unix_seconds(self) -> float`
  - `access_token_expired(self, skew_seconds: int) -> bool`

**Functions:**

- `load_credentials() -> Optional[GoogleCredentials]` — Load credentials from disk. Returns None if missing or corrupt.
- `save_credentials(creds: GoogleCredentials) -> Path` — Atomically write creds to disk with 0o600 permissions.
- `clear_credentials() -> None` — Remove the creds file. Idempotent.
- `exchange_code(code: str, verifier: str, redirect_uri: str, client_id: Optional[str], client_secret: Optional[str], timeout: float) -> Dict[str, Any]` — Exchange authorization code for access + refresh tokens.
- `refresh_access_token(refresh_token: str, client_id: Optional[str], client_secret: Optional[str], timeout: float) -> Dict[str, Any]` — Refresh the access token.
- `get_valid_access_token(force_refresh: bool) -> str` — Load creds, refreshing if near expiry, and return a valid bearer token.
- `update_project_ids(project_id: str, managed_project_id: str) -> None` — Persist resolved/discovered project IDs back into the credential file.
- `start_oauth_flow(force_relogin: bool, open_browser: bool, callback_wait_seconds: float, project_id: str) -> GoogleCredentials` — Run the interactive browser OAuth flow and persist credentials.
- `run_gemini_oauth_login_pure() -> Dict[str, Any]` — Run the login flow and return a dict matching the credential pool shape.
- `resolve_project_id_from_env() -> str` — Return a GCP project ID from env vars, in priority order.

### `agent/image_gen_provider.py`

_Image Generation Provider ABC_

**Classes:**

- **`ImageGenProvider`** — Abstract base class for an image generation backend.
  - `name(self) -> str`
  - `display_name(self) -> str`
  - `is_available(self) -> bool`
  - `list_models(self) -> List[Dict[str, Any]]`
  - `get_setup_schema(self) -> Dict[str, Any]`
  - `default_model(self) -> Optional[str]`
  - `generate(self, prompt: str, aspect_ratio: str) -> Dict[str, Any]`

**Functions:**

- `resolve_aspect_ratio(value: Optional[str]) -> str` — Clamp an aspect_ratio value to the valid set, defaulting to landscape.
- `save_b64_image(b64_data: str, prefix: str, extension: str) -> Path` — Decode base64 image data and write it under ``$VECTOR_HOME/cache/images/``.
- `success_response(image: str, model: str, prompt: str, aspect_ratio: str, provider: str, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]` — Build a uniform success response dict.
- `error_response(error: str, error_type: str, provider: str, model: str, prompt: str, aspect_ratio: str) -> Dict[str, Any]` — Build a uniform error response dict.

### `agent/image_gen_registry.py`

_Image Generation Provider Registry_

**Functions:**

- `register_provider(provider: ImageGenProvider) -> None` — Register an image generation provider.
- `list_providers() -> List[ImageGenProvider]` — Return all registered providers, sorted by name.
- `get_provider(name: str) -> Optional[ImageGenProvider]` — Return the provider registered under *name*, or None.
- `get_active_provider() -> Optional[ImageGenProvider]` — Resolve the currently-active provider.

### `agent/image_routing.py`

_Routing helpers for inbound user-attached images._

**Functions:**

- `decide_image_input_mode(provider: str, model: str, cfg: Optional[Dict[str, Any]]) -> str` — Return ``"native"`` or ``"text"`` for the given turn.
- `build_native_content_parts(user_text: str, image_paths: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]` — Build an OpenAI-style ``content`` list for a user turn.

### `agent/insights.py`

_Session Insights Engine for VectorCode._

**Classes:**

- **`InsightsEngine`** — Analyzes session history and produces usage insights.
  - `__init__(self, db)`
  - `generate(self, days: int, source: str) -> Dict[str, Any]`
  - `format_terminal(self, report: Dict) -> str`
  - `format_gateway(self, report: Dict) -> str`

### `agent/manual_compression_feedback.py`

_User-facing summaries for manual compression commands._

**Functions:**

- `summarize_manual_compression(before_messages: Sequence[dict[str, Any]], after_messages: Sequence[dict[str, Any]], before_tokens: int, after_tokens: int) -> dict[str, Any]` — Return consistent user-facing feedback for manual compression.

### `agent/memory_manager.py`

_MemoryManager — orchestrates the built-in memory provider plus at most_

**Classes:**

- **`StreamingContextScrubber`** — Stateful scrubber for streaming text that may contain split memory-context spans.
  - `__init__(self) -> None`
  - `reset(self) -> None`
  - `feed(self, text: str) -> str`
  - `flush(self) -> str`
- **`MemoryManager`** — Orchestrates the built-in provider plus at most one external provider.
  - `__init__(self) -> None`
  - `add_provider(self, provider: MemoryProvider) -> None`
  - `providers(self) -> List[MemoryProvider]`
  - `get_provider(self, name: str) -> Optional[MemoryProvider]`
  - `build_system_prompt(self) -> str`
  - `prefetch_all(self, query: str, session_id: str) -> str`
  - `queue_prefetch_all(self, query: str, session_id: str) -> None`
  - `sync_all(self, user_content: str, assistant_content: str, session_id: str) -> None`
  - _(+11 more methods)_

**Functions:**

- `sanitize_context(text: str) -> str` — Strip fence tags, injected context blocks, and system notes from provider output.
- `build_memory_context_block(raw_context: str) -> str` — Wrap prefetched memory in a fenced block with system note.

### `agent/memory_provider.py`

_Abstract base class for pluggable memory providers._

**Classes:**

- **`MemoryProvider`** — Abstract base class for memory providers.
  - `name(self) -> str`
  - `is_available(self) -> bool`
  - `initialize(self, session_id: str) -> None`
  - `system_prompt_block(self) -> str`
  - `prefetch(self, query: str, session_id: str) -> str`
  - `queue_prefetch(self, query: str, session_id: str) -> None`
  - `sync_turn(self, user_content: str, assistant_content: str, session_id: str) -> None`
  - `get_tool_schemas(self) -> List[Dict[str, Any]]`
  - _(+9 more methods)_

### `agent/model_metadata.py`

_Model metadata, context lengths, and token estimation utilities._

**Functions:**

- `is_local_endpoint(base_url: str) -> bool` — Return True if base_url points to a local machine.
- `detect_local_server_type(base_url: str, api_key: str) -> Optional[str]` — Detect which local server is running at base_url by probing known endpoints.
- `fetch_model_metadata(force_refresh: bool) -> Dict[str, Dict[str, Any]]` — Fetch model metadata from OpenRouter (cached for 1 hour).
- `fetch_endpoint_model_metadata(base_url: str, api_key: str, force_refresh: bool) -> Dict[str, Dict[str, Any]]` — Fetch model metadata from an OpenAI-compatible ``/models`` endpoint.
- `save_context_length(model: str, base_url: str, length: int) -> None` — Persist a discovered context length for a model+provider combo.
- `get_cached_context_length(model: str, base_url: str) -> Optional[int]` — Look up a previously discovered context length for model+provider.
- `get_next_probe_tier(current_length: int) -> Optional[int]` — Return the next lower probe tier, or None if already at minimum.
- `parse_context_limit_from_error(error_msg: str) -> Optional[int]` — Try to extract the actual context limit from an API error message.
- `parse_available_output_tokens_from_error(error_msg: str) -> Optional[int]` — Detect an "output cap too large" error and return how many output tokens are available.
- `query_ollama_num_ctx(model: str, base_url: str, api_key: str) -> Optional[int]` — Query an Ollama server for the model's context length.
- `get_model_context_length(model: str, base_url: str, api_key: str, config_context_length: int | None, provider: str, custom_providers: list | None) -> int` — Get the context length for a model.
- `estimate_tokens_rough(text: str) -> int` — Rough token estimate (~4 chars/token) for pre-flight checks.
- `estimate_messages_tokens_rough(messages: List[Dict[str, Any]]) -> int` — Rough token estimate for a message list (pre-flight only).
- `estimate_request_tokens_rough(messages: List[Dict[str, Any]], system_prompt: str, tools: Optional[List[Dict[str, Any]]]) -> int` — Rough token estimate for a full chat-completions request.

### `agent/models_dev.py`

_Models.dev registry integration — primary database for providers and models._

**Classes:**

- **`ModelInfo`** — Full metadata for a single model from models.dev.
  - `has_cost_data(self) -> bool`
  - `supports_vision(self) -> bool`
  - `supports_pdf(self) -> bool`
  - `supports_audio_input(self) -> bool`
  - `format_cost(self) -> str`
  - `format_capabilities(self) -> str`
- **`ProviderInfo`** — Full metadata for a provider from models.dev.
- **`ModelCapabilities`** — Structured capability metadata for a model from models.dev.

**Functions:**

- `fetch_models_dev(force_refresh: bool) -> Dict[str, Any]` — Fetch models.dev registry. In-memory cache (1hr) + disk fallback.
- `lookup_models_dev_context(provider: str, model: str) -> Optional[int]` — Look up context_length for a provider+model combo in models.dev.
- `get_model_capabilities(provider: str, model: str) -> Optional[ModelCapabilities]` — Look up full capability metadata from models.dev cache.
- `list_provider_models(provider: str) -> List[str]` — Return all model IDs for a provider from models.dev.
- `list_agentic_models(provider: str) -> List[str]` — Return model IDs suitable for agentic use from models.dev.
- `get_provider_info(provider_id: str) -> Optional[ProviderInfo]` — Get full provider metadata from models.dev.
- `get_model_info(provider_id: str, model_id: str) -> Optional[ModelInfo]` — Get full model metadata from models.dev.

### `agent/moonshot_schema.py`

_Helpers for translating OpenAI-style tool schemas to Moonshot's schema subset._

**Functions:**

- `sanitize_moonshot_tool_parameters(parameters: Any) -> Dict[str, Any]` — Normalize tool parameters to a Moonshot-compatible object schema.
- `sanitize_moonshot_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]` — Apply ``sanitize_moonshot_tool_parameters`` to every tool's parameters.
- `is_moonshot_model(model: str | None) -> bool` — True for any Kimi / Moonshot model slug, regardless of aggregator prefix.

### `agent/nous_rate_guard.py`

_Cross-session rate limit guard for Nous Portal._

**Functions:**

- `record_nous_rate_limit(headers: Optional[Mapping[str, str]], error_context: Optional[dict[str, Any]], default_cooldown: float) -> None` — Record that Nous Portal is rate-limited.
- `nous_rate_limit_remaining() -> Optional[float]` — Check if Nous Portal is currently rate-limited.
- `clear_nous_rate_limit() -> None` — Clear the rate limit state (e.g., after a successful Nous request).
- `format_remaining(seconds: float) -> str` — Format seconds remaining into human-readable duration.
- `is_genuine_nous_rate_limit(headers: Optional[Mapping[str, str]], last_known_state: Optional[Any]) -> bool` — Decide whether a 429 from Nous Portal is a real account rate limit.

### `agent/onboarding.py`

_Contextual first-touch onboarding hints._

**Functions:**

- `busy_input_hint_gateway(mode: str) -> str` — Hint shown the first time a user messages while the agent is busy.
- `busy_input_hint_cli(mode: str) -> str` — CLI version of the busy-input hint (plain text, no markdown).
- `tool_progress_hint_gateway() -> str`
- `tool_progress_hint_cli() -> str`
- `openclaw_residue_hint_cli() -> str` — Banner shown the first time VectorCode starts and finds ``~/.openclaw/``.
- `detect_openclaw_residue(home: Optional[Path]) -> bool` — Return True if an OpenClaw workspace directory is present in ``$HOME``.
- `is_seen(config: Mapping[str, Any], flag: str) -> bool` — Return True if the user has already been shown this first-touch hint.
- `mark_seen(config_path: Path, flag: str) -> bool` — Persist ``onboarding.seen.<flag> = True`` to ``config_path``.

### `agent/prompt_builder.py`

_System prompt assembly -- identity, platform hints, skills index, context files._

**Functions:**

- `build_environment_hints() -> str` — Return environment-specific guidance for the system prompt.
- `clear_skills_system_prompt_cache(clear_snapshot: bool) -> None` — Drop the in-process skills prompt cache (and optionally the disk snapshot).
- `build_skills_system_prompt(available_tools: 'set[str] | None', available_toolsets: 'set[str] | None') -> str` — Build a compact skill index for the system prompt.
- `build_nous_subscription_prompt(valid_tool_names: 'set[str] | None') -> str` — Build a compact Nous subscription capability block for the system prompt.
- `load_soul_md() -> Optional[str]` — Load SOUL.md from VECTOR_HOME and return its content, or None.
- `build_context_files_prompt(cwd: Optional[str], skip_soul: bool) -> str` — Discover and load context files for the system prompt.

### `agent/prompt_caching.py`

_Anthropic prompt caching (system_and_3 strategy)._

**Functions:**

- `apply_anthropic_cache_control(api_messages: List[Dict[str, Any]], cache_ttl: str, native_anthropic: bool) -> List[Dict[str, Any]]` — Apply system_and_3 caching strategy to messages for Anthropic models.

### `agent/rate_limit_tracker.py`

_Rate limit tracking for inference API responses._

**Classes:**

- **`RateLimitBucket`** — One rate-limit window (e.g. requests per minute).
  - `used(self) -> int`
  - `usage_pct(self) -> float`
  - `remaining_seconds_now(self) -> float`
- **`RateLimitState`** — Full rate-limit state parsed from response headers.
  - `has_data(self) -> bool`
  - `age_seconds(self) -> float`

**Functions:**

- `parse_rate_limit_headers(headers: Mapping[str, str], provider: str) -> Optional[RateLimitState]` — Parse x-ratelimit-* headers into a RateLimitState.
- `format_rate_limit_display(state: RateLimitState) -> str` — Format rate limit state for terminal/chat display.
- `format_rate_limit_compact(state: RateLimitState) -> str` — One-line compact summary for status bars / gateway messages.

### `agent/redact.py`

_Regex-based secret redaction for logs and tool output._

**Classes:**

- **`RedactingFormatter`** — Log formatter that redacts secrets from all log messages.
  - `__init__(self, fmt, datefmt, style)`
  - `format(self, record: logging.LogRecord) -> str`

**Functions:**

- `redact_sensitive_text(text: str) -> str` — Apply all redaction patterns to a block of text.

### `agent/retry_utils.py`

_Retry utilities — jittered backoff for decorrelated retries._

**Functions:**

- `jittered_backoff(attempt: int, base_delay: float, max_delay: float, jitter_ratio: float) -> float` — Compute a jittered exponential backoff delay.

### `agent/shell_hooks.py`

_Shell-script hooks bridge._

**Classes:**

- **`ShellHookSpec`** — Parsed and validated representation of a single ``hooks:`` entry.
  - `matches_tool(self, tool_name: Optional[str]) -> bool`

**Functions:**

- `register_from_config(cfg: Optional[Dict[str, Any]], accept_hooks: bool) -> List[ShellHookSpec]` — Register every configured shell hook on the plugin manager.
- `iter_configured_hooks(cfg: Optional[Dict[str, Any]]) -> List[ShellHookSpec]` — Return the parsed ``ShellHookSpec`` entries from config without
- `reset_for_tests() -> None` — Clear the idempotence set.  Test-only helper.
- `allowlist_path() -> Path` — Path to the per-user shell-hook allowlist file.
- `load_allowlist() -> Dict[str, Any]` — Return the parsed allowlist, or an empty skeleton if absent.
- `save_allowlist(data: Dict[str, Any]) -> None` — Atomically persist the allowlist via per-process ``mkstemp`` +
- `revoke(command: str) -> int` — Remove every allowlist entry matching ``command``.
- `allowlist_entry_for(event: str, command: str) -> Optional[Dict[str, Any]]` — Return the allowlist record for this pair, if any.
- `script_mtime_iso(command: str) -> Optional[str]` — ISO-8601 mtime of the resolved script path, or ``None`` if the
- `script_is_executable(command: str) -> bool` — Return ``True`` iff ``command`` is runnable as configured.
- `run_once(spec: ShellHookSpec, kwargs: Dict[str, Any]) -> Dict[str, Any]` — Fire a single shell-hook invocation with a synthetic payload.

### `agent/skill_commands.py`

_Shared slash command helpers for skills._

**Functions:**

- `scan_skill_commands() -> Dict[str, Dict[str, Any]]` — Scan ~/.vectorcode/skills/ and return a mapping of /command -> skill info.
- `get_skill_commands() -> Dict[str, Dict[str, Any]]` — Return the current skill commands mapping (scan first if empty).
- `resolve_skill_command_key(command: str) -> Optional[str]` — Resolve a user-typed /command to its canonical skill_cmds key.
- `build_skill_invocation_message(cmd_key: str, user_instruction: str, task_id: str | None, runtime_note: str) -> Optional[str]` — Build the user message content for a skill slash command invocation.
- `build_preloaded_skills_prompt(skill_identifiers: list[str], task_id: str | None) -> tuple[str, list[str], list[str]]` — Load one or more skills for session-wide CLI preloading.

### `agent/skill_preprocessing.py`

_Shared SKILL.md preprocessing helpers._

**Functions:**

- `load_skills_config() -> dict` — Load the ``skills`` section of config.yaml (best-effort).
- `substitute_template_vars(content: str, skill_dir: Path | None, session_id: str | None) -> str` — Replace ${VECTOR_SKILL_DIR} / ${VECTOR_SESSION_ID} in skill content.
- `run_inline_shell(command: str, cwd: Path | None, timeout: int) -> str` — Execute a single inline-shell snippet and return its stdout (trimmed).
- `expand_inline_shell(content: str, skill_dir: Path | None, timeout: int) -> str` — Replace every !`cmd` snippet in ``content`` with its stdout.
- `preprocess_skill_content(content: str, skill_dir: Path | None, session_id: str | None, skills_cfg: dict | None) -> str` — Apply configured SKILL.md template and inline-shell preprocessing.

### `agent/skill_utils.py`

_Lightweight skill metadata utilities shared by prompt_builder and skills_tool._

**Functions:**

- `yaml_load(content: str)` — Parse YAML with lazy import and CSafeLoader preference.
- `parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]` — Parse YAML frontmatter from a markdown string.
- `skill_matches_platform(frontmatter: Dict[str, Any]) -> bool` — Return True when the skill is compatible with the current OS.
- `get_disabled_skill_names(platform: str | None) -> Set[str]` — Read disabled skill names from config.yaml.
- `get_external_skills_dirs() -> List[Path]` — Read ``skills.external_dirs`` from config.yaml and return validated paths.
- `get_all_skills_dirs() -> List[Path]` — Return all skill directories: local ``~/.vectorcode/skills/`` first, then external.
- `extract_skill_conditions(frontmatter: Dict[str, Any]) -> Dict[str, List]` — Extract conditional activation fields from parsed frontmatter.
- `extract_skill_config_vars(frontmatter: Dict[str, Any]) -> List[Dict[str, Any]]` — Extract config variable declarations from parsed frontmatter.
- `discover_all_skill_config_vars() -> List[Dict[str, Any]]` — Scan all enabled skills and collect their config variable declarations.
- `resolve_skill_config_values(config_vars: List[Dict[str, Any]]) -> Dict[str, Any]` — Resolve current values for skill config vars from config.yaml.
- `extract_skill_description(frontmatter: Dict[str, Any]) -> str` — Extract a truncated description from parsed frontmatter.
- `iter_skill_index_files(skills_dir: Path, filename: str)` — Walk skills_dir yielding sorted paths matching *filename*.
- `parse_qualified_name(name: str) -> Tuple[Optional[str], str]` — Split ``'namespace:skill-name'`` into ``(namespace, bare_name)``.
- `is_valid_namespace(candidate: Optional[str]) -> bool` — Check whether *candidate* is a valid namespace (``[a-zA-Z0-9_-]+``).

### `agent/subdirectory_hints.py`

_Progressive subdirectory hint discovery._

**Classes:**

- **`SubdirectoryHintTracker`** — Track which directories the agent visits and load hints on first access.
  - `__init__(self, working_dir: Optional[str])`
  - `check_tool_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]`

### `agent/title_generator.py`

_Auto-generate short session titles from the first user/assistant exchange._

**Functions:**

- `generate_title(user_message: str, assistant_response: str, timeout: float, failure_callback: Optional[FailureCallback]) -> Optional[str]` — Generate a session title from the first exchange.
- `auto_title_session(session_db, session_id: str, user_message: str, assistant_response: str, failure_callback: Optional[FailureCallback]) -> None` — Generate and set a session title if one doesn't already exist.
- `maybe_auto_title(session_db, session_id: str, user_message: str, assistant_response: str, conversation_history: list, failure_callback: Optional[FailureCallback]) -> None` — Fire-and-forget title generation after the first exchange.

### `agent/trajectory.py`

_Trajectory saving utilities and static helpers._

**Functions:**

- `convert_scratchpad_to_think(content: str) -> str` — Convert <REASONING_SCRATCHPAD> tags to <think> tags.
- `has_incomplete_scratchpad(content: str) -> bool` — Check if content has an opening <REASONING_SCRATCHPAD> without a closing tag.
- `save_trajectory(trajectory: List[Dict[str, Any]], model: str, completed: bool, filename: str)` — Append a trajectory entry to a JSONL file.

### `agent/transports/anthropic.py`

_Anthropic Messages API transport._

**Classes:**

- **`AnthropicTransport`** — Transport for api_mode='anthropic_messages'.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> Any`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> Any`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]`
  - `map_finish_reason(self, raw_reason: str) -> str`

### `agent/transports/base.py`

_Abstract base for provider transports._

**Classes:**

- **`ProviderTransport`** — Base class for provider-specific format conversion and normalization.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> Any`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> Any`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]`
  - `map_finish_reason(self, raw_reason: str) -> str`

### `agent/transports/bedrock.py`

_AWS Bedrock Converse API transport._

**Classes:**

- **`BedrockTransport`** — Transport for api_mode='bedrock_converse'.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> Any`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> Any`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `map_finish_reason(self, raw_reason: str) -> str`

### `agent/transports/chat_completions.py`

_OpenAI Chat Completions transport._

**Classes:**

- **`ChatCompletionsTransport`** — Transport for api_mode='chat_completions'.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]`

### `agent/transports/codex.py`

_OpenAI Responses API (Codex) transport._

**Classes:**

- **`ResponsesApiTransport`** — Transport for api_mode='codex_responses'.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> Any`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> Any`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `preflight_kwargs(self, api_kwargs: Any, allow_stream: bool) -> dict`
  - `map_finish_reason(self, raw_reason: str) -> str`

### `agent/transports/types.py`

_Shared types for normalized provider responses._

**Classes:**

- **`ToolCall`** — A normalized tool call from any provider.
  - `type(self) -> str`
  - `function(self) -> 'ToolCall'`
  - `call_id(self) -> Optional[str]`
  - `response_item_id(self) -> Optional[str]`
  - `extra_content(self) -> Optional[Dict[str, Any]]`
- **`Usage`** — Token usage from an API response.
- **`NormalizedResponse`** — Normalized API response from any provider.
  - `reasoning_content(self) -> Optional[str]`
  - `reasoning_details(self)`
  - `codex_reasoning_items(self)`
  - `codex_message_items(self)`

**Functions:**

- `build_tool_call(id: Optional[str], name: str, arguments: Any) -> ToolCall` — Build a ``ToolCall``, auto-serialising *arguments* if it's a dict.
- `map_finish_reason(reason: Optional[str], mapping: Dict[str, str]) -> str` — Translate a provider-specific stop reason to the normalised set.

### `agent/usage_pricing.py`

**Classes:**

- **`CanonicalUsage`**
  - `prompt_tokens(self) -> int`
  - `total_tokens(self) -> int`
- **`BillingRoute`**
- **`PricingEntry`**
- **`CostResult`**

**Functions:**

- `resolve_billing_route(model_name: str, provider: Optional[str], base_url: Optional[str]) -> BillingRoute`
- `get_pricing_entry(model_name: str, provider: Optional[str], base_url: Optional[str], api_key: Optional[str]) -> Optional[PricingEntry]`
- `normalize_usage(response_usage: Any, provider: Optional[str], api_mode: Optional[str]) -> CanonicalUsage` — Normalize raw API response usage into canonical token buckets.
- `estimate_usage_cost(model_name: str, usage: CanonicalUsage, provider: Optional[str], base_url: Optional[str], api_key: Optional[str]) -> CostResult`
- `has_known_pricing(model_name: str, provider: Optional[str], base_url: Optional[str], api_key: Optional[str]) -> bool` — Check whether we have pricing data for this model+route.
- `format_duration_compact(seconds: float) -> str`
- `format_token_count_compact(value: int) -> str`


---

## (root)

### `agent_types.py`

_VectorCode agent type definitions — 60+ specialized agents._


---

## agents

### `agents/agent.py`

_VectorCode v3 Agent — domain entity for the agent lifecycle system._

**Classes:**

- **`Agent`**
  - `__init__(self, agent_id: str, agent_type: str, capabilities: Optional[list[str]], role: Optional[str], parent: Optional[str], metadata: Optional[dict])`
  - `can_execute(self, task_type: str) -> bool`
  - `assign_task(self, task: Any) -> None`
  - `complete_task(self) -> None`
  - `fail_task(self) -> None`
  - `terminate(self) -> None`
  - `to_dict(self) -> dict`

### `agents/coordinator.py`

_VectorCode v3 SwarmCoordinator — multi-agent coordination with topologies._

**Classes:**

- **`SwarmCoordinator`**
  - `__init__(self, topology: str)`
  - `initialize(self)`
  - `shutdown(self)`
  - `spawn_agent(self, agent_type: str) -> Agent`
  - `get_agent(self, agent_id: str) -> Optional[Agent]`
  - `list_agents(self, status: Optional[str]) -> list[Agent]`
  - `assign_task(self, task: dict) -> Optional[str]`
  - `complete_task(self, task_id: str, result: Any)`
  - _(+1 more methods)_

### `agents/loader.py`

_Load agent definitions from YAML/TOML files, and from legacy agent_types.py._

**Functions:**

- `load_yaml_definition(path: Path) -> 'AgentDefinition'` — Load a single YAML file into an AgentDefinition.
- `load_toml_definition(path: Path) -> 'AgentDefinition'` — Load a TOML file with an [agent] section into an AgentDefinition.
- `definitions_from_agent_types() -> list['AgentDefinition']` — Convert the hardcoded agent_types.py into a list of AgentDefinition objects.

### `agents/registry.py`

_Runtime agent registry — register/get/list agents by name._

**Classes:**

- **`AgentDefinition`** — Metadata for a single VECTOR agent.
- **`AgentRegistry`** — Registry that stores and queries AgentDefinition objects by name.
  - `__init__(self) -> None`
  - `register(self, defn: AgentDefinition) -> None`
  - `get(self, name: str) -> Optional[AgentDefinition]`
  - `list_all(self) -> list[AgentDefinition]`
  - `search(self, query: str) -> list[AgentDefinition]`
  - `load_from_yaml(self, path: Path) -> int`
  - `load_from_directory(self, dir: Path) -> int`

**Functions:**

- `get_registry() -> AgentRegistry` — Return the global AgentRegistry singleton.

### `agents/workflow_engine.py`

_VectorCode v3 WorkflowEngine — task execution pipeline with lifecycle._

**Classes:**

- **`WorkflowEngine`**
  - `__init__(self)`
  - `execute(self, workflow: dict) -> dict`


---

## api

### `api/server.py`

_OpenAI-compatible API server — connects any OpenAI-compatible frontend to VectorCode._

**Classes:**

- **`APIServer`**
  - `__init__(self, host: str, port: int)`
  - `on_chat(self, callback)`
  - `start(self)`
  - `stop(self)`


---

## (root)

### `autonomous.py`

_VectorAutonomous — VectorCode VC-4 Mode B. TaskQueue-based autonomous agent._

**Classes:**

- **`VectorAutonomous`** — Mode B: submits GSD tasks as HIGH-priority TaskQueue items and returns immediately.
  - `__init__(self) -> None`
  - `submit(self, task: str) -> str`


---

## (root)

### `batch_runner.py`

_Batch Agent Runner_

**Classes:**

- **`BatchRunner`** — Manages batch processing of agent prompts with checkpointing and statistics.
  - `__init__(self, dataset_file: str, batch_size: int, run_name: str, distribution: str, max_iterations: int, base_url: str, api_key: str, model: str, num_workers: int, verbose: bool, ephemeral_system_prompt: str, log_prefix_chars: int, providers_allowed: List[str], providers_ignored: List[str], providers_order: List[str], provider_sort: str, max_tokens: int, reasoning_config: Dict[str, Any], prefill_messages: List[Dict[str, Any]], max_samples: int)`
  - `run(self, resume: bool)`

**Functions:**

- `main(dataset_file: str, batch_size: int, run_name: str, distribution: str, model: str, api_key: str, base_url: str, max_turns: int, num_workers: int, resume: bool, verbose: bool, list_distributions: bool, ephemeral_system_prompt: str, log_prefix_chars: int, providers_allowed: str, providers_ignored: str, providers_order: str, provider_sort: str, max_tokens: int, reasoning_effort: str, reasoning_disabled: bool, prefill_messages_file: str, max_samples: int)` — Run batch processing of agent prompts from a dataset.


---

## cli

### `cli/auth.py`

_Credential management — add, remove, list, test API credentials._

**Classes:**

- **`CredentialEntry`**
- **`AuthManager`** — Manages API credentials for VectorCode providers.
  - `__init__(self) -> None`
  - `add(self, name: str, provider: str, api_key: str) -> dict`
  - `remove(self, name: str) -> dict`
  - `list_credentials(self) -> list[CredentialEntry]`
  - `get(self, name: str) -> Optional[str]`
  - `test(self, name: str) -> dict`
  - `from_env(self) -> list[CredentialEntry]`

**Functions:**

- `get_auth_manager() -> 'AuthManager'` — Return singleton AuthManager.
- `handle_auth(args) -> None` — Dispatch auth subcommands from argparse args.

### `cli/completion.py`

_Shell completion scripts for the `vector` CLI command._

**Functions:**

- `get_completion_script(shell: str) -> str` — Return completion script for given shell (bash/zsh/fish).
- `get_install_instructions(shell: str) -> str` — Return human-readable instructions for installing completions.
- `auto_install(shell: str | None) -> str` — Detect current shell and install completions automatically.

### `cli/doctor.py`

_Doctor — diagnostics for VectorCode installation._

**Classes:**

- **`CheckResult`**
- **`Doctor`** — Runs diagnostic checks and prints a health report for VectorCode.
  - `run_all(self) -> list[CheckResult]`
  - `check_python_version(self) -> CheckResult`
  - `check_ollama(self) -> CheckResult`
  - `check_ollama_models(self) -> CheckResult`
  - `check_vector_home(self) -> CheckResult`
  - `check_core_deps(self) -> CheckResult`
  - `check_optional_deps(self) -> CheckResult`
  - `check_vectormd(self) -> CheckResult`
  - _(+3 more methods)_

**Functions:**

- `run_doctor() -> None` — Run all checks and print the report.

### `cli/profiles.py`

_Named profiles — switch between different VectorCode configurations._

**Classes:**

- **`Profile`**
- **`ProfileManager`** — Manages named VectorCode profiles.
  - `__init__(self) -> None`
  - `create(self, name: str) -> Profile`
  - `delete(self, name: str) -> dict`
  - `use(self, name: str) -> Profile`
  - `current(self) -> Profile`
  - `list_profiles(self) -> list[Profile]`
  - `show(self, name: Optional[str]) -> dict`
  - `get(self, name: str) -> Optional[Profile]`

**Functions:**

- `get_profile_manager() -> 'ProfileManager'` — Return singleton ProfileManager.
- `handle_profile(args) -> None` — Dispatch profile subcommands from argparse args.

### `cli/self_update.py`

_vector self-update — upgrade VectorCode from PyPI._

**Functions:**

- `get_current_version() -> str`
- `get_latest_pypi_version() -> Optional[str]`
- `self_update(docker: bool) -> int` — Upgrade VectorCode to the latest version.


---

## (root)

### `cli.py`

_VectorCode CLI — entry point._

**Functions:**

- `cmd_repl(_args)`
- `cmd_auto(args)`
- `cmd_hybrid(_args)`
- `cmd_mcp(args)`
- `cmd_run(args)` — One-shot non-interactive task. Reads from stdin if no task given.
- `cmd_status(_args)`
- `cmd_sessions(args)`
- `cmd_models(args)`
- `cmd_agents(args)`
- `cmd_skills(args)` — Handle `vector skills` subcommands.
- `cmd_auth(args)` — Handle `vector auth` subcommands.
- `cmd_profile(args)` — Handle `vector profile` subcommands.
- `cmd_doctor(_args)` — Handle `vector doctor` subcommand.
- `cmd_completion(args)` — Handle `vector completion` subcommand.
- `cmd_usage(args)` — Print usage analytics from session DB.
- _(+11 more functions)_


---

## (root)

### `cli_commands.py`

_VectorCode CLI commands — consolidated from VectorCode 52+ CLI files._

**Functions:**

- `cmd_version(args)`
- `cmd_status(args)` — Show status of all components.
- `cmd_doctor(args)` — Check configuration and dependencies.
- `cmd_setup(args)` — Interactive setup wizard.
- `cmd_logs(args)` — Show recent logs.
- `cmd_backup(args)` — Backup configuration and data.
- `cmd_completion(args)` — Generate shell completion script.
- `cmd_update(args)` — Update VectorCode to latest version.
- `run_cli_command(cmd_name: str, args: Optional[dict])`


---

## comms

### `comms/acp_client.py`

_ACP (Agent Communication Protocol) client — editor integration shim._

**Classes:**

- **`ACPServer`** — ACP protocol server — listens on HTTP and forwards to VectorCode.
  - `__init__(self, host: str, port: int)`
  - `start(self)`
  - `stop(self)`

### `comms/bluebubbles_bot.py`

_BlueBubbles iMessage adapter — connects to local macOS BlueBubbles server._

**Classes:**

- **`BlueBubblesBot`**
  - `__init__(self, server_url: str, password: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, chat_guid: str, text: str)`
  - `stop(self)`

### `comms/dingtalk_bot.py`

_DingTalk adapter — Stream Mode via dingtalk-stream SDK._

**Classes:**

- **`DingTalkBot`**
  - `__init__(self, client_id: str, client_secret: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, conversation_id: str, text: str)`
  - `stop(self)`

### `comms/discord_bot.py`

_Discord bot adapter — webhook mode (always works) + bot mode (full features)._

**Classes:**

- **`DiscordWebhook`** — Send messages to Discord via a webhook URL.  No bot token required.
  - `__init__(self, webhook_url: str) -> None`
  - `send(self, content: str, username: str, embed: dict | None) -> dict`
  - `send_embed(self, title: str, description: str, color: int, fields: list[dict] | None) -> dict`
  - `send_code(self, code: str, language: str) -> dict`
- **`DiscordBot`** — Full Discord bot using discord.py.  Supports message handling and sending.
  - `__init__(self, token: str, command_prefix: str) -> None`
  - `on_message(self, callback: Callable) -> None`
  - `start(self) -> None`
  - `send(self, channel_id: int, content: str) -> None`
  - `send_embed(self, channel_id: int, title: str, description: str, color: int) -> None`
  - `stop(self) -> None`

**Functions:**

- `create_discord_adapter(mode: str, token: str, webhook_url: str) -> DiscordBot | DiscordWebhook` — Create and return the appropriate Discord adapter.

### `comms/email_client.py`

_Email client — IMAP receive + SMTP send with graceful degradation._

**Classes:**

- **`EmailMessage`**
- **`EmailClient`**
  - `__init__(self, imap_host: str, imap_port: int, imap_user: str, imap_pass: str, smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str, use_ssl: bool) -> None`
  - `connect_imap(self) -> bool`
  - `disconnect_imap(self) -> None`
  - `fetch_unread(self, folder: str, limit: int) -> list[EmailMessage]`
  - `search(self, query: str, folder: str, limit: int) -> list[EmailMessage]`
  - `send(self, to: str | list[str], subject: str, body: str, html_body: str, reply_to_uid: str, attachments: list[str] | None) -> dict`
  - `mark_read(self, uid: str, folder: str) -> None`
  - `mark_unread(self, uid: str, folder: str) -> None`
  - _(+1 more methods)_

**Functions:**

- `get_email_client() -> EmailClient` — Return a module-level singleton EmailClient.

### `comms/feishu_bot.py`

_Feishu/Lark adapter — WebSocket + Webhook + Comment + Card interaction._

**Classes:**

- **`FeishuBot`**
  - `__init__(self, app_id: str, app_secret: str, verification_token: str)`
  - `on_message(self, callback: Callable)`
  - `set_comment_handler(self, handler)`
  - `start(self)`
  - `send_text(self, chat_id: str, text: str)`
  - `send_card(self, chat_id: str, title: str, body: str)`
  - `upload_image(self, image_path: str) -> Optional[str]`
  - `handle_webhook(self, body: dict) -> dict`
  - _(+1 more methods)_

### `comms/feishu_comment.py`

_Feishu comment handler — Drive doc comment threads with AI reply._

**Classes:**

- **`FeishuCommentHandler`**
  - `__init__(self, app_id: str, app_secret: str)`
  - `on_comment(self, callback: Callable)`
  - `handle_event(self, event: dict)`
  - `reply_to_comment(self, doc_token: str, comment_id: str, text: str)`

### `comms/gateway_helpers.py`

_Gateway helpers — deduplication, markdown stripping, thread tracking._

**Classes:**

- **`MessageDeduplicator`** — TTL-based message deduplication cache.
  - `__init__(self, max_size: int, ttl: float)`
  - `is_duplicate(self, msg_id: str) -> bool`

**Functions:**

- `strip_markdown(text: str) -> str` — Strip markdown formatting for plain-text platforms.

### `comms/homeassistant_bot.py`

_Home Assistant adapter — WebSocket API for smart home control._

**Classes:**

- **`HomeAssistantBot`**
  - `__init__(self, url: str, token: str)`
  - `connect(self)`
  - `get_state(self, entity_id: str) -> Optional[dict]`
  - `call_service(self, domain: str, service: str, data: Optional[dict])`
  - `stop(self)`

### `comms/inbound.py`

_InboundMessageRouter — routes incoming messages from all platforms to VectorCode._

**Classes:**

- **`InboundMessage`** — Platform-neutral normalized inbound message.
- **`RouteResult`** — Result of routing an InboundMessage.
- **`InboundMessageRouter`** — Routes incoming messages from any platform to the correct handler.
  - `__init__(self)`
  - `on_command(self, command: str, fn: Callable) -> None`
  - `on_platform(self, platform: str, fn: Callable) -> None`
  - `on_keyword(self, keyword: str, fn: Callable) -> None`
  - `set_default(self, fn: Callable) -> None`
  - `route(self, msg: InboundMessage) -> RouteResult`
  - `bridge_to_repl(self, repl_fn: Callable) -> None`
  - `get_thread(self, thread_id: str, limit: int) -> list[InboundMessage]`
  - _(+1 more methods)_

### `comms/matrix_bot.py`

_Matrix adapter — homeserver-agnostic chat via mautrix SDK._

**Classes:**

- **`MatrixBot`**
  - `__init__(self, homeserver: str, token: str, user_id: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, room_id: str, text: str)`
  - `stop(self)`

### `comms/mattermost_bot.py`

_Mattermost adapter — REST API v4 + WebSocket integration._

**Classes:**

- **`MattermostBot`**
  - `__init__(self, url: str, token: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, channel_id: str, text: str)`
  - `get_channels(self, team_id: str) -> list`
  - `stop(self)`

### `comms/messenger.py`

_MessagingHub — absorbed from reference MessagingAdapter._

**Classes:**

- **`MessagingHub`** — Standalone multi-platform messaging hub.
  - `__init__(self)`
  - `send_notification(self, text: str, priority: str) -> dict`
  - `send_to_channel(self, channel: str, text: str, priority: str) -> dict`
  - `send_to_telegram(self, chat_id: str, text: str, priority: str) -> dict`
  - `schedule_cron_job(self, schedule: str, message: str, platform: str, channel: str) -> dict`
  - `list_cron_jobs(self) -> list[dict]`
  - `delete_cron_job(self, job_id: str) -> bool`
  - `register_skill(self, skill_name: str, skill_content: str) -> dict`
  - _(+9 more methods)_

### `comms/platform_adapters.py`

_PlatformAdapters — multi-platform send adapters for VectorCode._

**Classes:**

- **`WhatsAppAdapter`** — Meta Cloud API for WhatsApp Business.
  - `__init__(self, phone_number_id: str, access_token: str)`
  - `send(self, to: str, text: str) -> bool`
  - `send_template(self, to: str, template_name: str, language: str) -> bool`
- **`MatrixAdapter`** — Matrix protocol via HTTP Client-Server API (no matrix-nio dependency).
  - `__init__(self, homeserver: str, access_token: str)`
  - `send(self, room_id: str, text: str) -> bool`
- **`SignalAdapter`** — signal-cli REST bridge (https://github.com/bbernhard/signal-cli-rest-api).
  - `__init__(self, host: str, sender: str)`
  - `send(self, recipients: list[str], text: str) -> bool`
- **`MattermostAdapter`** — Mattermost incoming webhook + REST API.
  - `__init__(self, webhook_url: str, token: Optional[str], base_url: Optional[str])`
  - `send_webhook(self, text: str, channel: Optional[str], username: str) -> bool`
  - `send_rest(self, channel_id: str, text: str) -> bool`
- **`HomeAssistantAdapter`** — Home Assistant webhook trigger or persistent_notification service.
  - `__init__(self, base_url: str, token: str)`
  - `notify(self, title: str, message: str, notification_id: str) -> bool`
  - `fire_event(self, event_type: str, data: Optional[dict]) -> bool`
  - `webhook(self, webhook_id: str, data: Optional[dict]) -> bool`
- **`DingTalkAdapter`** — DingTalk group robot webhook with HMAC-SHA256 signature.
  - `__init__(self, webhook_url: str, secret: Optional[str])`
  - `send(self, text: str, at_all: bool) -> bool`
  - `send_markdown(self, title: str, text: str) -> bool`
- **`FeishuAdapter`** — Feishu (Lark) custom bot webhook.
  - `__init__(self, webhook_url: str)`
  - `send(self, text: str) -> bool`
  - `send_card(self, title: str, content: str) -> bool`
- **`WeComAdapter`** — WeCom (Enterprise WeChat) group robot webhook.
  - `__init__(self, webhook_url: str)`
  - `send(self, text: str, mentioned_list: Optional[list]) -> bool`
  - `send_markdown(self, content: str) -> bool`
- **`SMSAdapter`** — SMS via Twilio or AWS SNS.
  - `__init__(self, provider: str, twilio_sid: str, twilio_token: str, twilio_from: str, sns_region: str)`
  - `send(self, to: str, body: str) -> bool`
- **`PlatformRegistry`** — Unified registry for all platform adapters.
  - `__init__(self)`
  - `register(self, name: str, adapter: object) -> None`
  - `get(self, name: str) -> Optional[object]`
  - `send(self, platform: str) -> bool`
  - `list_platforms(self) -> list[str]`

### `comms/qq_bot.py`

_QQ Bot adapter — Tencent QQ channel bot via WebSocket/HTTP._

**Classes:**

- **`QQBot`**
  - `__init__(self, app_id: str, token: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, channel_id: str, text: str)`
  - `stop(self)`

### `comms/session_manager.py`

_SessionManager — cross-platform conversation session state for VectorCode._

**Classes:**

- **`PlatformSession`** — Conversation state for a single (platform, chat_id) pair.
  - `to_dict(self) -> dict`
- **`SessionManager`** — Thread-safe session manager for multi-platform VectorCode deployments.
  - `__init__(self) -> None`
  - `get_or_create(self, platform: str, user_id: str, chat_id: str) -> PlatformSession`
  - `get(self, session_id: str) -> Optional[PlatformSession]`
  - `get_history(self, session_id: str) -> list`
  - `append_message(self, session_id: str, role: str, content: str) -> None`
  - `clear(self, session_id: str) -> None`
  - `expire_old(self) -> int`
  - `list_active(self) -> list`
  - _(+3 more methods)_

**Functions:**

- `get_session_manager() -> SessionManager` — Return the module-level SessionManager singleton (thread-safe).

### `comms/signal_bot.py`

_Signal messenger adapter — connects to signal-cli daemon HTTP mode._

**Classes:**

- **`SignalBot`**
  - `__init__(self, http_url: str, account: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, recipient: str, text: str)`
  - `stop(self)`

### `comms/slack_bot.py`

_Slack bot adapter using slack-bolt Socket Mode._

**Classes:**

- **`SlackBot`**
  - `__init__(self, bot_token: str, app_token: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, channel: str, text: str)`
  - `stop(self)`

### `comms/sms_bot.py`

_SMS adapter — Twilio-based SMS send/receive._

**Classes:**

- **`SMSBot`**
  - `__init__(self, account_sid: str, auth_token: str, from_number: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, to: str, text: str)`
  - `stop(self)`

### `comms/telegram_bot.py`

_TelegramBot — bidirectional Telegram Bot API integration for VectorCode._

**Classes:**

- **`TelegramMessage`**
  - `__init__(self, data: dict)`
  - `command(self) -> Optional[str]`
  - `args(self) -> str`
  - `sender_name(self) -> str`
- **`TelegramBot`** — Long-polling Telegram bot for VectorCode.
  - `__init__(self, token: str, allowed_chat_ids: Optional[set])`
  - `on_command(self, command: str, fn: Callable) -> None`
  - `on_text(self, fn: Callable) -> None`
  - `send(self, chat_id: int, text: str, reply_to: Optional[int], parse_mode: str, keyboard: Optional[list]) -> bool`
  - `reply(self, msg: TelegramMessage, text: str) -> bool`
  - `broadcast(self, text: str, chat_ids: Optional[list]) -> int`
  - `start(self) -> None`
  - `stop(self) -> None`
  - _(+1 more methods)_

### `comms/telegram_network.py`

_Telegram network utilities — MTProto helpers, proxy, and connection management._

**Functions:**

- `get_bot_info(token: str) -> Optional[dict]` — Get bot information from Telegram API.
- `set_webhook(token: str, url: str) -> bool` — Set a webhook URL for the Telegram bot.

### `comms/webhook_server.py`

_Generic inbound webhook server — FastAPI-based, signature verification, event routing._

**Classes:**

- **`WebhookEvent`**
- **`WebhookServer`** — FastAPI-based inbound webhook server with HMAC signature verification.
  - `__init__(self, host: str, port: int, path_prefix: str) -> None`
  - `register_secret(self, platform: str, secret: str) -> None`
  - `on_event(self, event_type: str | list[str], callback: Callable) -> None`
  - `on_any(self, callback: Callable) -> None`
  - `build_app(self) -> Any`
  - `start(self) -> None`
  - `stop(self) -> None`

**Functions:**

- `get_webhook_server(port: int) -> WebhookServer` — Return a module-level singleton WebhookServer on *port*.

### `comms/wechat_bot.py`

_WeChat adapter — Tencent iLink Bot API integration._

**Classes:**

- **`WeChatBot`**
  - `__init__(self, bot_id: str, token: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, user_id: str, text: str)`
  - `stop(self)`

### `comms/wecom_bot.py`

_WeCom (Enterprise WeChat) adapter — AI Bot WebSocket gateway._

**Classes:**

- **`WeComBot`**
  - `__init__(self, bot_id: str, secret: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, user_id: str, text: str)`
  - `stop(self)`

### `comms/wecom_callback.py`

_WeCom callback verification — URL verification and event callback handling._

**Classes:**

- **`WeComCallback`**
  - `__init__(self, token: str, encoding_aes_key: str, corp_id: str)`
  - `verify_url(self, msg_signature: str, timestamp: str, nonce: str, echo_str: str) -> Optional[str]`
  - `parse_callback_xml(self, xml_data: str) -> dict`

### `comms/wecom_crypto.py`

_WeCom BizMsgCrypt — AES-CBC encryption for callback mode._

**Classes:**

- **`WeComCryptoError`**
- **`SignatureError`**
- **`DecryptError`**
- **`EncryptError`**
- **`PKCS7Encoder`**
  - `encode(cls, text: bytes) -> bytes`
  - `decode(cls, decrypted: bytes) -> bytes`
- **`WXBizMsgCrypt`**
  - `__init__(self, token: str, encoding_aes_key: str, receive_id: str)`
  - `decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bytes`
  - `encrypt(self, plaintext: str, nonce: Optional[str], timestamp: Optional[str]) -> str`

### `comms/whatsapp_bot.py`

_WhatsApp adapter — Business API and web-based backends._

**Classes:**

- **`WhatsAppBot`**
  - `__init__(self, api_key: str, phone_id: str, backend: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, to: str, text: str)`
  - `stop(self)`

### `comms/yuanbao_bot.py`

_Yuanbao adapter — WebSocket gateway with AUTH_BIND and heartbeat._

**Classes:**

- **`YuanbaoBot`**
  - `__init__(self, app_id: str, app_secret: str, bot_id: str)`
  - `on_message(self, callback: Callable)`
  - `start(self)`
  - `send(self, user_id: str, text: str)`
  - `stop(self)`

### `comms/yuanbao_media.py`

_Yuanbao media handler — COS upload, TIM media message building._

**Functions:**

- `upload_image(image_path: str, api_domain: str, app_id: str, app_secret: str) -> Optional[str]` — Upload image to COS and return URL.
- `upload_file(file_path: str, api_domain: str, app_id: str, app_secret: str) -> Optional[str]` — Upload a file to COS.

### `comms/yuanbao_proto.py`

_Yuanbao protocol — message serialization/deserialization for WebSocket transport._

**Functions:**

- `encode_message(msg_type: int, payload: dict, seq: int) -> bytes` — Encode a Yuanbao protocol message.
- `decode_message(data: bytes) -> dict` — Decode a Yuanbao protocol message.

### `comms/yuanbao_sticker.py`

_Yuanbao sticker handler — sticker send/receive for Yuanbao platform._

**Classes:**

- **`StickerInfo`**
  - `__init__(self, sticker_id: str, pack_id: str, url: str)`

**Functions:**

- `send_sticker(bot, user_id: str, sticker: StickerInfo) -> bool` — Send a sticker to a Yuanbao user.


---

## config

### `config/env_detector.py`

_Detect runtime environment — Termux, WSL, Docker, bare Linux, Windows, macOS._

**Classes:**

- **`Environment`** — Enumeration of supported runtime environments.
- **`EnvInfo`** — Snapshot of the detected runtime environment and available capabilities.
  - `adjust_paths(self) -> dict[str, str]`

**Functions:**

- `detect() -> EnvInfo` — Detect and return the current runtime EnvInfo (not cached).
- `get_env() -> EnvInfo` — Return a cached EnvInfo — calls detect() on first access.

### `config/theme.py`

_Color theme engine — ANSI color schemes for VectorCode terminal output._

**Classes:**

- **`ColorTheme`**
- **`ThemeEngine`** — Manages the active color theme.  Respects NO_COLOR env var.
  - `__init__(self) -> None`
  - `use(self, name: str) -> 'ColorTheme'`
  - `current(self) -> ColorTheme`
  - `list_themes(self) -> list[str]`
  - `add_theme(self, theme: ColorTheme) -> None`
  - `colorize(self, text: str, style: str) -> str`
  - `strip_ansi(self, text: str) -> str`
  - `save_theme(self, theme: ColorTheme) -> None`

**Functions:**

- `get_theme_engine() -> ThemeEngine` — Singleton accessor.
- `colorize(text: str, style: str) -> str` — Colorize text using the active theme.
- `c_primary(text: str) -> str`
- `c_secondary(text: str) -> str`
- `c_success(text: str) -> str`
- `c_warning(text: str) -> str`
- `c_error(text: str) -> str`
- `c_info(text: str) -> str`
- `c_bold(text: str) -> str`
- `c_dim(text: str) -> str`
- `c_tool(text: str) -> str`
- `c_file(text: str) -> str`
- `c_code(text: str) -> str`


---

## (root)

### `config.py`

_VectorCode TOML-based configuration system._

**Classes:**

- **`VectorConfig`** — Merged TOML configuration for VectorCode.
  - `__init__(self, project_dir: Path | None) -> None`
  - `get(self, default)`
  - `default_model(self) -> str`
  - `fast_model(self) -> str`
  - `local_model(self) -> str`
  - `max_iterations(self) -> int`
  - `permission_mode(self) -> str`
  - `auto_compact_threshold(self) -> float`
  - _(+4 more methods)_
- **`ModelRegistry`** — Persistent cache of probed model capabilities (~/.config/vector/model-registry.json).
  - `__init__(self) -> None`
  - `get(self, model_id: str) -> dict | None`
  - `set(self, model_id: str, caps: dict) -> None`


---

## context

### `context/compactor.py`

_Enhanced context compaction pipeline for VectorCode._

**Classes:**

- **`ContextCompactor`** — VectorCode context compaction pipeline.
  - `__init__(self, model: str, project_dir: Path | None, threshold_chars: int, summary_target_ratio: float) -> None`
  - `needs_compaction(self, messages: list[dict]) -> bool`
  - `compact(self, messages: list[dict]) -> list[dict]`

### `context/engine.py`

_Context engine — token-aware conversation compression._

**Classes:**

- **`ContextEngine`** — Base class for context management strategies.
  - `name(self) -> str`
  - `update_from_response(self, usage: dict) -> None`
  - `should_compress(self, prompt_tokens: Optional[int]) -> bool`
  - `compress(self, messages: list, current_tokens: Optional[int], focus_topic: Optional[str]) -> list`
  - `has_content_to_compress(self, messages: list) -> bool`
  - `on_session_start(self, session_id: str) -> None`
  - `on_session_end(self, session_id: str, messages: list) -> None`
  - `on_session_reset(self) -> None`
  - _(+2 more methods)_
- **`ContextCompressor`** — Default compressor — priority-based retention with summary injection.
  - `name(self) -> str`
  - `__init__(self, context_length: int, threshold_percent: float, protect_first_n: int, protect_last_n: int)`
  - `update_from_response(self, usage: dict) -> None`
  - `should_compress(self, prompt_tokens: Optional[int]) -> bool`
  - `compress(self, messages: list, current_tokens: Optional[int], focus_topic: Optional[str]) -> list`

**Functions:**

- `priority_retain(messages: list[dict], budget_tokens: int, model_context_length: int, tail_n: int) -> list[dict]` — Retain messages within budget_tokens by dropping lowest-priority ones first.
- `get_context_engine(model_id: str, context_length: int) -> ContextCompressor` — Return a pre-configured ContextCompressor for the given model.

### `context/prompt_builder.py`

_System prompt assembly — identity, platform hints, skills, context files._

**Functions:**

- `build_system_prompt(identity: str, personality: Optional[str], skills_index: str, project_context: str, tool_list: str, platform_hints: str) -> str` — Assemble the system prompt from components.
- `build_tool_list(tools: list[dict]) -> str` — Build a formatted tool list string from tool metadata.
- `load_project_context(project_dir: Optional[Path]) -> str` — Load VECTOR.md project config if it exists.

### `context/references.py`

_Context references — ported from reference context_references.py._

**Classes:**

- **`ContextReference`** — A single @mention parsed from a user message.
- **`ContextReferenceResult`** — Result of expanding all @references in a message.

**Functions:**

- `parse_context_references(message: str) -> List[ContextReference]` — Find all @references in a message and return them as ContextReference objects.
- `expand_context_references(message: str, cwd: Path) -> ContextReferenceResult` — Replace all @references in message with their content.

### `context/session_memory.py`

_Session memory auto-generator — writes/updates .vector/memory.md._

**Functions:**

- `update_session_memory(messages: list[dict]) -> None` — Extract learnings from messages and merge into .vector/memory.md.
- `read_memory_md() -> str` — Return the contents of .vector/memory.md as a string.

### `context/trajectory_compressor.py`

_Trajectory compressor — 6-stage token-budget-aware context compression._

**Functions:**

- `estimate_tokens(text: str) -> int` — Rough char/4 token estimate — always >= 1.
- `prune_tool_results(messages: list[dict], max_tool_chars: int) -> list[dict]` — Truncate tool_result content that exceeds max_tool_chars.
- `group_into_turns(messages: list[dict]) -> list[list[dict]]` — Group consecutive messages into logical turns.
- `score_turn(turn: list[dict], index: int, total: int) -> float` — Compute importance score 0.0–1.0 for a turn.
- `drop_turns(turns: list[list[dict]], scores: list[float], target_tokens: int) -> tuple[list[list[dict]], list[int]]` — Drop lowest-scoring turns until total estimated tokens ≤ target_tokens.
- `stitch_turns(kept_turns: list[list[dict]], dropped_gaps: list[int]) -> list[dict]` — Reassemble kept turns into a flat message list.
- `validate(messages: list[dict]) -> list[dict]` — Remove orphaned tool_result messages.
- `compress_trajectory(messages: list[dict], target_tokens: int, head_protection: int, tail_protection: int) -> list[dict]` — Run all 6 compression stages and return a token-budget-aware message list.

### `context/vectormd.py`

_VECTOR.md reader — loads the project config file into session context._

**Classes:**

- **`VectorMD`** — Reads VECTOR.md from a project directory.
  - `__init__(self, project_dir: str | Path) -> None`
  - `path(self) -> Path`
  - `exists(self) -> bool`
  - `load(self) -> str`
  - `as_system_block(self) -> str`
  - `create_default(self, project_name: str) -> None`
  - `inject_into_messages(self, messages: list[dict]) -> list[dict]`

**Functions:**

- `scan_for_injection(content: str, filename: str) -> str` — Scan context file content for prompt injection. Returns sanitized content.


---

## (root)

### `credential_sources.py`

_Credential sources — registry for removing credentials from 9 external locations._

**Classes:**

- **`CredentialSource`**
- **`RemovalResult`**
- **`RemovalStep`**
- **`CredentialSourceRegistry`** — Registry of removal steps for each credential source.
  - `__init__(self) -> None`
  - `execute_removal(self, credential_name: str) -> list[RemovalResult]`
  - `suppress_source(self, source: CredentialSource) -> None`
  - `is_suppressed(self, source: CredentialSource) -> bool`
  - `list_steps(self) -> list[dict]`

**Functions:**

- `atomic_json_write(path: Path, data: dict) -> None` — Write JSON atomically using a temp file + os.replace().
- `get_credential_source_registry() -> CredentialSourceRegistry` — Return the singleton CredentialSourceRegistry.


---

## (root)

### `credentials.py`

_VectorCode credential pool — multi-key failover with cooldown persistence._

**Classes:**

- **`PooledCredential`** — A single API key entry inside a CredentialPool.
  - `is_available(self) -> bool`
  - `from_env(cls, provider: str, var_name: str) -> 'Optional[PooledCredential]'`
  - `from_config(cls, provider: str, label: str, api_key: str, base_url: str) -> 'PooledCredential'`
  - `to_status_dict(self) -> dict`
  - `apply_status_dict(self, d: dict) -> None`
- **`CredentialPool`** — Manages a set of credentials for one provider.
  - `__init__(self, provider: str, entries: List[PooledCredential], strategy: str) -> None`
  - `select(self) -> Optional[PooledCredential]`
  - `mark_exhausted(self, credential_id: str, status_code: int, retry_after_seconds: float) -> Optional[PooledCredential]`
  - `mark_error(self, credential_id: str, error_code: int) -> None`
  - `reset_all(self) -> int`
  - `add(self, cred: PooledCredential) -> None`
  - `has_available(self) -> bool`
  - `entries(self) -> list`
  - _(+3 more methods)_
- **`CredentialManager`** — Singleton manager for all provider credential pools.
  - `get(cls) -> 'CredentialManager'`
  - `__init__(self) -> None`
  - `load_from_config(self, config: dict) -> None`
  - `get_pool(self, provider: str) -> Optional[CredentialPool]`
  - `select(self, provider: str) -> Optional[PooledCredential]`
  - `on_rate_limit(self, provider: str, credential_id: str, retry_after: float) -> Optional[PooledCredential]`
  - `on_auth_error(self, provider: str, credential_id: str) -> Optional[PooledCredential]`
  - `status_report(self) -> str`

**Functions:**

- `get_credential_manager() -> CredentialManager` — Return the singleton CredentialManager, loading config on first call.


---

## cron

### `cron/jobs.py`

_Cron job storage and management._

**Functions:**

- `ensure_dirs()` — Ensure cron directories exist with secure permissions.
- `parse_duration(s: str) -> int` — Parse duration string into minutes.
- `parse_schedule(schedule: str) -> Dict[str, Any]` — Parse schedule string into structured format.
- `compute_next_run(schedule: Dict[str, Any], last_run_at: Optional[str]) -> Optional[str]` — Compute the next run time for a schedule.
- `load_jobs() -> List[Dict[str, Any]]` — Load all jobs from storage.
- `save_jobs(jobs: List[Dict[str, Any]])` — Save all jobs to storage.
- `create_job(prompt: str, schedule: str, name: Optional[str], repeat: Optional[int], deliver: Optional[str], origin: Optional[Dict[str, Any]], skill: Optional[str], skills: Optional[List[str]], model: Optional[str], provider: Optional[str], base_url: Optional[str], script: Optional[str], context_from: Optional[Union[str, List[str]]], enabled_toolsets: Optional[List[str]], workdir: Optional[str]) -> Dict[str, Any]` — Create a new cron job.
- `get_job(job_id: str) -> Optional[Dict[str, Any]]` — Get a job by ID.
- `list_jobs(include_disabled: bool) -> List[Dict[str, Any]]` — List all jobs, optionally including disabled ones.
- `update_job(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]` — Update a job by ID, refreshing derived schedule fields when needed.
- `pause_job(job_id: str, reason: Optional[str]) -> Optional[Dict[str, Any]]` — Pause a job without deleting it.
- `resume_job(job_id: str) -> Optional[Dict[str, Any]]` — Resume a paused job and compute the next future run from now.
- `trigger_job(job_id: str) -> Optional[Dict[str, Any]]` — Schedule a job to run on the next scheduler tick.
- `remove_job(job_id: str) -> bool` — Remove a job by ID.
- `mark_job_run(job_id: str, success: bool, error: Optional[str], delivery_error: Optional[str])` — Mark a job as having been run.
- _(+3 more functions)_

### `cron/scheduler.py`

_Cron job scheduler - executes due jobs._

**Functions:**

- `run_job(job: dict) -> tuple[bool, str, str, Optional[str]]` — Execute a single cron job.
- `tick(verbose: bool, adapters, loop) -> int` — Check and run all due jobs.


---

## display

### `display/diff_preview.py`

_ANSI-colored diff preview for file edits and patches._

**Classes:**

- **`DiffStats`**

**Functions:**

- `render_diff(old_content: str, new_content: str, filename: str, context_lines: int, max_lines: int) -> str` — Render a unified diff between *old_content* and *new_content* with ANSI color.
- `render_patch(patch_text: str, max_lines: int) -> str` — Render an already-computed unified diff patch string with ANSI color.
- `diff_stats(old_content: str, new_content: str) -> DiffStats` — Count additions and deletions in a diff.
- `build_tool_preview(tool_name: str, args: dict, result: Optional[str]) -> str` — Build a human-readable, ANSI-colored preview of a tool call and its result.
- `format_tool_result(tool_name: str, result: str, max_lines: int) -> str` — Format a tool result for display. Truncates long outputs.

### `display/renderer.py`

_Central display renderer — coordinates spinner, diff preview, and output._

**Classes:**

- **`VectorRenderer`** — Stateful renderer for a VectorCode session.
  - `__init__(self, use_color: bool, verbose: bool) -> None`
  - `on_tool_start(self, tool_name: str, args: dict) -> None`
  - `on_tool_end(self, tool_name: str, args: dict, result: str) -> None`
  - `on_response(self, text: str) -> None`
  - `snapshot_file(self, path: str) -> None`
  - `show_diff(self, path: str, new_content: str) -> None`
  - `print_tool_call(self, tool_name: str, args: dict) -> None`
  - `print_error(self, message: str) -> None`
  - _(+1 more methods)_

**Functions:**

- `get_renderer() -> VectorRenderer` — Return the process-level singleton VectorRenderer.

### `display/spinner.py`

_Animated spinner with per-tool emoji and status messages._

**Classes:**

- **`VectorSpinner`** — Thread-based spinner that writes to stderr.
  - `__init__(self, message: str, tool_name: str) -> None`
  - `start(self) -> 'VectorSpinner'`
  - `stop(self, final_message: str) -> None`
  - `update(self, message: str, tool_name: str) -> None`

**Functions:**

- `get_tool_emoji(tool_name: str) -> str` — Return the emoji associated with *tool_name*.
- `get_tool_message(tool_name: str) -> str` — Return a random status message for *tool_name*.


---

## engine

### `engine/agent.py`

_AIAgent — main agent class. Orchestrates the think→act→observe loop._

**Classes:**

- **`AIAgent`** — AI Agent with tool calling capabilities.
  - `__init__(self, base_url: Optional[str], api_key: Optional[str], provider: Optional[str], model: str, max_iterations: int, tool_delay: float, iteration_budget: Optional[IterationBudget], enabled_toolsets: Optional[List[str]], disabled_toolsets: Optional[List[str]], session_id: Optional[str], session_db, parent_session_id: Optional[str], tool_progress_callback: Optional[Callable], tool_start_callback: Optional[Callable], tool_complete_callback: Optional[Callable], thinking_callback: Optional[Callable], stream_delta_callback: Optional[Callable], status_callback: Optional[Callable], ephemeral_system_prompt: Optional[str], platform: Optional[str], user_id: Optional[str], user_name: Optional[str], save_trajectories: bool, verbose_logging: bool, quiet_mode: bool, credential_pool, permission_gateway, memory_manager, toolset: str)`
  - `run_conversation(self, user_message: str) -> Dict[str, Any]`

### `engine/agent_loop.py`

_VectorCode Agent Loop — ported from VectorCode run_agent.py core._

**Classes:**

- **`IterationBudget`** — Thread-safe iteration counter. Parent default=90, subagent default=50.
  - `__init__(self, max_total: int)`
  - `consume(self) -> bool`
  - `refund(self) -> None`
  - `used(self) -> int`
  - `remaining(self) -> int`
- **`VectorAgent`** — VectorCode's agent execution loop — ported from VectorCode AIAgent.
  - `__init__(self, model_id: str, max_iterations: int, project_dir: Optional[Path], session_id: Optional[str], iteration_budget: Optional[IterationBudget], platform: str, quiet_mode: bool, save_trajectories: bool, tool_start_callback: Optional[Callable], tool_complete_callback: Optional[Callable], step_callback: Optional[Callable], stream_delta_callback: Optional[Callable], clarify_callback: Optional[Callable], approval_callback: Optional[Callable])`
  - `get_tool_schemas(self) -> list[dict]`
  - `run_conversation(self, user_message: str, system_message: str, conversation_history: Optional[List[Dict]], task_id: Optional[str]) -> Dict[str, Any]`

**Functions:**

- `make_agent(model_id: str, project_dir: Optional[Path], max_iterations: int, quiet_mode: bool) -> VectorAgent` — Factory — creates a VectorAgent with sensible defaults.

### `engine/budget.py`

_Thread-safe iteration counter for an agent._

**Classes:**

- **`IterationBudget`** — Thread-safe iteration counter.
  - `__init__(self, max_total: int)`
  - `consume(self) -> bool`
  - `refund(self) -> None`
  - `used(self) -> int`
  - `remaining(self) -> int`

### `engine/conversation.py`

_The main think→act→observe loop._

**Functions:**

- `run_conversation_loop(agent: 'AIAgent', user_message: str) -> Dict[str, Any]` — Core think→act→observe loop.

### `engine/max_iter.py`

_Handle graceful budget exhaustion._

**Functions:**

- `handle_max_iterations(agent: 'AIAgent', partial_text: str) -> Dict[str, Any]` — Called when iteration budget is exhausted.

### `engine/recovery.py`

_Error recovery with credential pool rotation._

**Functions:**

- `recover_on_error(agent: 'AIAgent', error: Exception) -> Optional[Any]` — Try to recover from a provider error via credential rotation.

### `engine/safety.py`

_Safety utilities: SafeWriter, surrogate sanitization, destructive command detection._

**Functions:**

- `install_safe_stdio() -> None` — Wrap stdout/stderr so best-effort console output cannot crash the agent.

### `engine/tool_exec.py`

_Tool execution: sequential, concurrent, and parallel-safety detection._

**Functions:**

- `execute_tool_calls_sequential(tool_calls: list, dispatch_fn: Callable[[str, dict, Any], Any], context: Any) -> list` — Execute tool calls one at a time, returning list of results.
- `execute_tool_calls_concurrent(tool_calls: list, dispatch_fn: Callable[[str, dict, Any], Any], context: Any, max_workers: int) -> list` — Execute tool calls in parallel (only call when _should_parallelize returns True).


---

## (root)

### `errors.py`

_API error classifier — absorbed from reference agent/error_classifier.py._

**Classes:**

- **`FailoverReason`** — Why an API call failed — determines recovery strategy.
- **`ClassifiedError`**
  - `is_auth(self) -> bool`

**Functions:**

- `classify_error(exc: Exception, status_code: Optional[int], provider: str, model: str) -> ClassifiedError` — Classify an API exception into a FailoverReason with recovery hints.


---

## gateway

### `gateway/channel_directory.py`

_Channel directory -- cached map of reachable channels/contacts per platform._

**Functions:**

- `build_channel_directory(adapters: Dict[Any, Any]) -> Dict[str, Any]` — Build a channel directory from connected platform adapters and session data.
- `load_directory() -> Dict[str, Any]` — Load the cached channel directory from disk.
- `lookup_channel_type(platform_name: str, chat_id: str) -> Optional[str]` — Return the channel ``type`` string (e.g. ``"channel"``, ``"forum"``) for *chat_id*, or *None* if unknown.
- `resolve_channel_name(platform_name: str, name: str) -> Optional[str]` — Resolve a human-friendly channel name to a numeric ID.
- `format_directory_for_display() -> str` — Format the channel directory as a human-readable list for the model.

### `gateway/config.py`

_Gateway configuration management._

**Classes:**

- **`Platform`** — Supported messaging platforms.
- **`HomeChannel`** — Default destination for a platform.
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'HomeChannel'`
- **`SessionResetPolicy`** — Controls when sessions reset (lose context).
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'SessionResetPolicy'`
- **`PlatformConfig`** — Configuration for a single messaging platform.
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'PlatformConfig'`
- **`StreamingConfig`** — Configuration for real-time token streaming to messaging platforms.
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'StreamingConfig'`
- **`GatewayConfig`** — Main gateway configuration.
  - `get_connected_platforms(self) -> List[Platform]`
  - `get_home_channel(self, platform: Platform) -> Optional[HomeChannel]`
  - `get_reset_policy(self, platform: Optional[Platform], session_type: Optional[str]) -> SessionResetPolicy`
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'GatewayConfig'`
  - `get_unauthorized_dm_behavior(self, platform: Optional[Platform]) -> str`

**Functions:**

- `load_gateway_config() -> GatewayConfig` — Load gateway configuration from multiple sources.

### `gateway/delivery.py`

_Delivery routing for cron job outputs and agent responses._

**Classes:**

- **`DeliveryTarget`** — A single delivery target.
  - `parse(cls, target: str, origin: Optional[SessionSource]) -> 'DeliveryTarget'`
  - `to_string(self) -> str`
- **`DeliveryRouter`** — Routes messages to appropriate destinations.
  - `__init__(self, config: GatewayConfig, adapters: Dict[Platform, Any])`
  - `deliver(self, content: str, targets: List[DeliveryTarget], job_id: Optional[str], job_name: Optional[str], metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]`

### `gateway/display_config.py`

_Per-platform display/verbosity configuration resolver._

**Functions:**

- `resolve_display_setting(user_config: dict, platform_key: str, setting: str, fallback: Any) -> Any` — Resolve a display setting with per-platform override support.

### `gateway/hooks.py`

_Event Hook System_

**Classes:**

- **`HookRegistry`** — Discovers, loads, and fires event hooks.
  - `__init__(self)`
  - `loaded_hooks(self) -> List[dict]`
  - `discover_and_load(self) -> None`
  - `emit(self, event_type: str, context: Optional[Dict[str, Any]]) -> None`
  - `emit_collect(self, event_type: str, context: Optional[Dict[str, Any]]) -> List[Any]`

### `gateway/mirror.py`

_Session mirroring for cross-platform message delivery._

**Functions:**

- `mirror_to_session(platform: str, chat_id: str, message_text: str, source_label: str, thread_id: Optional[str], user_id: Optional[str]) -> bool` — Append a delivery-mirror message to the target session's transcript.

### `gateway/pairing.py`

_DM Pairing System_

**Classes:**

- **`PairingStore`** — Manages pairing codes and approved user lists.
  - `__init__(self)`
  - `is_approved(self, platform: str, user_id: str) -> bool`
  - `list_approved(self, platform: str) -> list`
  - `revoke(self, platform: str, user_id: str) -> bool`
  - `generate_code(self, platform: str, user_id: str, user_name: str) -> Optional[str]`
  - `approve_code(self, platform: str, code: str) -> Optional[dict]`
  - `list_pending(self, platform: str) -> list`
  - `clear_pending(self, platform: str) -> int`

### `gateway/restart.py`

_Shared gateway restart constants and parsing helpers._

**Functions:**

- `parse_restart_drain_timeout(raw: object) -> float` — Parse a configured drain timeout, falling back to the shared default.

### `gateway/run.py`

_Gateway runner - entry point for messaging platform integrations._

**Classes:**

- **`GatewayRunner`** — Main gateway controller.
  - `__init__(self, config: Optional[GatewayConfig])`
  - `should_exit_cleanly(self) -> bool`
  - `should_exit_with_failure(self) -> bool`
  - `exit_reason(self) -> Optional[str]`
  - `exit_code(self) -> Optional[int]`
  - `request_restart(self, detached: bool, via_service: bool) -> bool`
  - `start(self) -> bool`
  - `stop(self, restart: bool, detached_restart: bool, service_restart: bool) -> None`
  - _(+1 more methods)_

**Functions:**

- `start_gateway(config: Optional[GatewayConfig], replace: bool, verbosity: Optional[int]) -> bool` — Start the gateway and run until interrupted.
- `main()` — CLI entry point for the gateway.

### `gateway/server.py`

_VectorCode HTTP Gateway — REST API for agent execution._

**Classes:**

- **`RunRequest`**
- **`RunResponse`**
- **`GatewayServer`** — VectorCode HTTP gateway — exposes agent execution over REST + SSE.
  - `__init__(self, host: str, port: int) -> None`
  - `build_app(self) -> Any`
  - `start(self) -> None`
  - `stop(self) -> None`

**Functions:**

- `get_gateway_server(port: int) -> GatewayServer` — Return the module-level singleton GatewayServer, creating it if needed.

### `gateway/session.py`

_Session management for the gateway._

**Classes:**

- **`SessionSource`** — Describes where a message originated from.
  - `description(self) -> str`
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'SessionSource'`
- **`SessionContext`** — Full context for a session, used for dynamic system prompt injection.
  - `to_dict(self) -> Dict[str, Any]`
- **`SessionEntry`** — Entry in the session store.
  - `to_dict(self) -> Dict[str, Any]`
  - `from_dict(cls, data: Dict[str, Any]) -> 'SessionEntry'`
- **`SessionStore`** — Manages session storage and retrieval.
  - `__init__(self, sessions_dir: Path, config: GatewayConfig, has_active_processes_fn)`
  - `has_any_sessions(self) -> bool`
  - `get_or_create_session(self, source: SessionSource, force_new: bool) -> SessionEntry`
  - `update_session(self, session_key: str, last_prompt_tokens: int) -> None`
  - `suspend_session(self, session_key: str) -> bool`
  - `mark_resume_pending(self, session_key: str, reason: str) -> bool`
  - `clear_resume_pending(self, session_key: str) -> bool`
  - `prune_old_entries(self, max_age_days: int) -> int`
  - _(+8 more methods)_

**Functions:**

- `build_session_context_prompt(context: SessionContext, redact_pii: bool) -> str` — Build the dynamic system prompt section that tells the agent about its context.
- `is_shared_multi_user_session(source: SessionSource, group_sessions_per_user: bool, thread_sessions_per_user: bool) -> bool` — Return True when a non-DM session is shared across participants.
- `build_session_key(source: SessionSource, group_sessions_per_user: bool, thread_sessions_per_user: bool) -> str` — Build a deterministic session key from a message source.
- `build_session_context(source: SessionSource, config: GatewayConfig, session_entry: Optional[SessionEntry]) -> SessionContext` — Build a full session context from a source and config.

### `gateway/session_context.py`

_Session-scoped context variables for the VectorCode gateway._

**Functions:**

- `set_session_vars(platform: str, chat_id: str, chat_name: str, thread_id: str, user_id: str, user_name: str, session_key: str) -> list` — Set all session context variables and return reset tokens.
- `clear_session_vars(tokens: list) -> None` — Mark session context variables as explicitly cleared.
- `get_session_env(name: str, default: str) -> str` — Read a session context variable by its legacy ``VECTOR_SESSION_*`` name.

### `gateway/status.py`

_Gateway runtime status helpers._

**Functions:**

- `terminate_pid(pid: int, force: bool) -> None` — Terminate a PID with platform-appropriate force semantics.
- `get_process_start_time(pid: int) -> Optional[int]` — Public wrapper for retrieving a process start time when available.
- `acquire_gateway_runtime_lock() -> bool` — Claim the cross-process runtime lock for the gateway.
- `release_gateway_runtime_lock() -> None` — Release the gateway runtime lock when owned by this process.
- `is_gateway_runtime_lock_active(lock_path: Optional[Path]) -> bool` — Return True when some process currently owns the gateway runtime lock.
- `write_pid_file() -> None` — Write the current process PID and metadata to the gateway PID file.
- `write_runtime_status(gateway_state: Any, exit_reason: Any, restart_requested: Any, active_agents: Any, platform: Any, platform_state: Any, error_code: Any, error_message: Any) -> None` — Persist gateway runtime health information for diagnostics/status.
- `read_runtime_status() -> Optional[dict[str, Any]]` — Read the persisted gateway runtime health/status information.
- `remove_pid_file() -> None` — Remove the gateway PID file, but only if it belongs to this process.
- `acquire_scoped_lock(scope: str, identity: str, metadata: Optional[dict[str, Any]]) -> tuple[bool, Optional[dict[str, Any]]]` — Acquire a machine-local lock keyed by scope + identity.
- `release_scoped_lock(scope: str, identity: str) -> None` — Release a previously-acquired scope lock when owned by this process.
- `release_all_scoped_locks(owner_pid: Optional[int], owner_start_time: Optional[int]) -> int` — Remove scoped lock files in the lock directory.
- `write_takeover_marker(target_pid: int) -> bool` — Record that ``target_pid`` is being replaced by the current process.
- `consume_takeover_marker_for_self() -> bool` — Check & unlink the takeover marker if it names the current process.
- `clear_takeover_marker() -> None` — Remove the takeover marker unconditionally. Safe to call repeatedly.
- _(+2 more functions)_

### `gateway/sticker_cache.py`

_Sticker description cache for Telegram._

**Functions:**

- `get_cached_description(file_unique_id: str) -> Optional[dict]` — Look up a cached sticker description.
- `cache_sticker_description(file_unique_id: str, description: str, emoji: str, set_name: str) -> None` — Store a sticker description in the cache.
- `build_sticker_injection(description: str, emoji: str, set_name: str) -> str` — Build the warm-style injection text for a sticker description.
- `build_animated_sticker_injection(emoji: str) -> str` — Build injection text for animated/video stickers we can't analyze.

### `gateway/stream_consumer.py`

_Gateway streaming consumer — bridges sync agent callbacks to async platform delivery._

**Classes:**

- **`StreamConsumerConfig`** — Runtime config for a single stream consumer instance.
- **`GatewayStreamConsumer`** — Async consumer that progressively edits a platform message with streamed tokens.
  - `__init__(self, adapter: Any, chat_id: str, config: Optional[StreamConsumerConfig], metadata: Optional[dict])`
  - `already_sent(self) -> bool`
  - `final_response_sent(self) -> bool`
  - `on_segment_break(self) -> None`
  - `on_commentary(self, text: str) -> None`
  - `on_delta(self, text: str) -> None`
  - `finish(self) -> None`
  - `run(self) -> None`

### `gateway/whatsapp_identity.py`

_Shared helpers for canonicalising WhatsApp sender identity._

**Functions:**

- `normalize_whatsapp_identifier(value: str) -> str` — Strip WhatsApp JID/LID syntax down to its stable numeric identifier.
- `expand_whatsapp_aliases(identifier: str) -> Set[str]` — Resolve WhatsApp phone/LID aliases via bridge session mapping files.
- `canonical_whatsapp_identifier(identifier: str) -> str` — Return a stable WhatsApp sender identity across phone-JID/LID variants.

### `gateway/ws.py`

_WebSocket transport for VectorCode gateway — real-time streaming._

**Classes:**

- **`WSMessage`**
- **`VectorWSHandler`** — WebSocket handler that bridges a VectorAgent session to a WebSocket connection.
  - `__init__(self, websocket: Any, session_id: str) -> None`
  - `handle(self) -> None`
  - `send_token(self, content: str) -> None`
  - `send_tool_call(self, name: str, args: dict, call_id: str) -> None`
  - `send_tool_result(self, content: str, call_id: str) -> None`
  - `send_done(self, response: str) -> None`
  - `send_error(self, message: str) -> None`
  - `request_approval(self, action_id: str, action_desc: str) -> bool`

**Functions:**

- `create_ws_route(app: Any, path: str) -> None` — Add a WebSocket route to a FastAPI app.


---

## (root)

### `gsd_loop.py`

_GSDLoop — VectorCode VC-3. discuss→plan→execute→verify workflow._

**Classes:**

- **`GSDPhase`**
- **`GSDLoop`** — Discuss→Plan→Execute→Verify loop for VectorCode task execution.
  - `__init__(self, mode: str) -> None`
  - `should_skip_discuss(self, task: str) -> bool`
  - `advance(self) -> None`
  - `reset(self) -> None`
  - `run(self, task: str) -> dict`


---

## hooks

### `hooks/registry.py`

_HookRegistry — VectorCode VC-5._

**Classes:**

- **`HookName`**
- **`HookRegistry`** — Central registry for VectorCode lifecycle hooks.
  - `__init__(self, default_timeout: float) -> None`
  - `register(self, hook: HookName, fn: Callable, priority: int) -> None`
  - `unregister(self, hook: HookName, fn: Callable) -> None`
  - `fire(self, hook: HookName, ctx: dict) -> None`
  - `list_handlers(self, hook: HookName) -> List[Callable]`
- **`PluginManifest`** — Parsed contents of a plugin's plugin.toml manifest.
- **`PluginRegistry`** — Discovers and manages VectorCode plugins from ~/.vector/plugins/.
  - `__init__(self) -> None`
  - `discover(self) -> List[str]`
  - `invoke_hook(self, hook_name: str) -> List[dict]`
  - `list_plugins(self) -> List[dict]`
  - `enable(self, name: str) -> None`
  - `disable(self, name: str) -> None`

**Functions:**

- `get_plugin_registry() -> 'PluginRegistry'` — Return the module-level PluginRegistry singleton.

### `hooks/shell_hooks.py`

_Shell hooks runner — absorbed from reference agent/shell_hooks.py._

**Classes:**

- **`HookResult`**
  - `__init__(self, blocked, reason, injected_context, stdout, exit_code)`
- **`ShellHookRunner`** — Runs shell-script hooks from vector.toml [hooks] configuration.
  - `__init__(self, hooks: Dict[str, List[str]], auto_accept: bool, timeout: int, cwd: str)`
  - `from_config(cls, cfg: dict) -> 'ShellHookRunner'`
  - `has_hooks(self, event: str) -> bool`
  - `invoke(self, event: str, tool_name: str, tool_input: Any, session_id: str, extra: Optional[Dict]) -> HookResult`

### `hooks/workers.py`

_BackgroundWorkers — VectorCode VC-5 with real worker implementations._

**Classes:**

- **`Priority`**
- **`TaskQueue`** — Minimal singleton task queue.
  - `get(cls) -> 'TaskQueue'`
  - `submit(self, fn: Callable, priority: Priority, name: str) -> str`
- **`WorkerName`**
- **`BackgroundWorkers`** — 12 background workers submitted as LOW-priority TaskQueue items.
  - `__init__(self) -> None`
  - `submit(self, worker: WorkerName) -> str`
  - `list_workers(self) -> List[WorkerName]`
  - `run_ultralearn(self) -> None`
  - `run_optimize(self) -> dict`
  - `run_consolidate(self) -> dict`
  - `run_predict(self) -> dict`
  - `run_audit(self) -> dict`
  - _(+7 more methods)_


---

## (root)

### `hybrid.py`

_VectorHybrid — VectorCode VC-4 Mode C. Autonomous with checkpoint gates._

**Classes:**

- **`CheckpointGate`**
- **`VectorHybrid`** — Mode C: autonomous execution with asyncio.Event checkpoint gates at
  - `__init__(self) -> None`
  - `needs_approval(self, action: str) -> bool`
  - `disable_checkpoint(self, gate: CheckpointGate) -> None`
  - `enable_checkpoint(self, gate: CheckpointGate) -> None`


---

## (root)

### `insights.py`

_Usage analytics — VectorCode implementation._

**Classes:**

- **`InsightsEngine`** — Analyzes session history from ~/.vector/sessions.db.
  - `__init__(self, db_path: Path | None) -> None`
  - `generate(self, days: int) -> dict[str, Any]`
  - `format_terminal(self, days: int) -> str`
  - `estimate_cost(self, model: str, input_tokens: int, output_tokens: int, cache_read: int) -> float`


---

## mcp

### `mcp/protocol_manager.py`

_MCP protocol manager — tool discovery, version negotiation, lifecycle._

**Functions:**

- `create_server(name: str) -> MCPServer`
- `get_server(name: str) -> MCPServer`
- `create_transport(server: MCPServer, transport_type: str) -> MCPTransport`

### `mcp/server.py`

_VectorCode v3 MCP Server — expose tools, config, and memory via MCP protocol._

**Classes:**

- **`MCPTool`**
  - `__init__(self, name: str, description: str, handler: callable, input_schema: Optional[dict])`
- **`MCPServer`**
  - `__init__(self)`
  - `register_tool(self, tool: MCPTool)`
  - `list_tools(self) -> list[dict]`
  - `call_tool(self, name: str, args: dict) -> dict`
  - `create_agent_tools(self, coordinator) -> list[MCPTool]`
  - `create_memory_tools(self, backend) -> list[MCPTool]`

### `mcp/transports.py`

_MCP transports — stdio and HTTP transport implementations._

**Classes:**

- **`MCPTransport`**
  - `__init__(self, handler: Callable)`
  - `handle(self, message: dict) -> dict`
- **`StdioTransport`**
  - `run(self)`
- **`HTTPTransport`**
  - `__init__(self, handler: Callable, host: str, port: int)`
  - `run(self)`


---

## mcp_client

### `mcp_client/bridge.py`

_VectorCode MCP bridge — group-based tool routing to multiple MCP servers._

**Classes:**

- **`MCPBridge`** — Routes tool calls to the appropriate MCP server based on tool group.
  - `__init__(self)`
  - `get_or_connect(self, server_name: str) -> Any`
  - `call_tool(self, tool_name: str, arguments: dict, server: Optional[str]) -> Any`
  - `list_all_tools(self) -> List[dict]`

**Functions:**

- `get_group_for_tool(tool_name: str) -> Optional[str]` — Return the group name for a tool based on its prefix.
- `is_tool_enabled(tool_name: str) -> bool` — Return True if the tool's group is enabled.
- `get_bridge() -> MCPBridge`

### `mcp_client/client.py`

_VectorCode MCP CLIENT — connects to external MCP servers via stdio._

**Classes:**

- **`StdioMCPClient`** — MCP client that talks to a server subprocess over stdin/stdout.
  - `__init__(self, name: str, command: str, args: Optional[List[str]], env: Optional[Dict[str, str]], tool_timeout: float, connect_timeout: float) -> None`
  - `start(self) -> bool`
  - `stop(self) -> None`
  - `list_tools(self) -> List[Dict[str, Any]]`
  - `call_tool(self, name: str, arguments: Dict[str, Any]) -> str`
- **`MCPClientRegistry`** — Registry of MCP server connections for VectorCode.
  - `__init__(self) -> None`
  - `add_server(self, name: str, command: str, args: Optional[List[str]], env: Optional[Dict[str, str]], tool_timeout: float, connect_timeout: float) -> None`
  - `add_from_config(self, config_list: List[Dict[str, Any]]) -> None`
  - `start_all(self) -> Dict[str, bool]`
  - `stop_all(self) -> None`
  - `get_all_tools(self) -> List[Dict[str, Any]]`
  - `call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str`
  - `get_client(self, server_name: str) -> Optional[StdioMCPClient]`

**Functions:**

- `get_mcp_registry() -> MCPClientRegistry` — Return the process-wide MCPClientRegistry singleton.


---

## (root)

### `mcp_serve.py`

_VectorCode MCP Server — expose messaging conversations as MCP tools._

**Classes:**

- **`QueueEvent`** — An event in the bridge's in-memory queue.
- **`EventBridge`** — Background poller that watches SessionDB for new messages and
  - `__init__(self)`
  - `start(self)`
  - `stop(self)`
  - `poll_events(self, after_cursor: int, session_key: Optional[str], limit: int) -> dict`
  - `wait_for_event(self, after_cursor: int, session_key: Optional[str], timeout_ms: int) -> Optional[dict]`
  - `list_pending_approvals(self) -> List[dict]`
  - `respond_to_approval(self, approval_id: str, decision: str) -> dict`

**Functions:**

- `create_mcp_server(event_bridge: Optional[EventBridge]) -> 'FastMCP'` — Create and return the VectorCode MCP server with all tools registered.
- `run_mcp_server(verbose: bool) -> None` — Start the VectorCode MCP server on stdio.


---

## memory

### `memory/auto_bridge.py`

_AutoMemoryBridge — bidirectional sync between EpisodicMemory and FAISSIndex._

**Classes:**

- **`AutoMemoryBridge`** — Bidirectional bridge between episodic memory and FAISS vector index.
  - `__init__(self, index_path: str) -> None`
  - `sync_episodic_to_faiss(self) -> int`
  - `sync_faiss_to_episodic(self) -> int`
  - `start_background_sync(self) -> None`

### `memory/backends.py`

_VectorCode v3 Memory backends — SQLite, Hybrid, AgentDB persistence._

**Classes:**

- **`SQLiteBackend`**
  - `__init__(self, db_path: Optional[Path])`
  - `store(self, namespace: str, key: str, value: Any, ttl: float)`
  - `get(self, namespace: str, key: str) -> Optional[Any]`
  - `search(self, namespace: str, query: str) -> list[dict]`
- **`HybridBackend`**
  - `__init__(self, sqlite_path: Optional[Path])`
  - `store(self, namespace: str, key: str, value: Any, ttl: float)`
  - `get(self, namespace: str, key: str) -> Optional[Any]`
  - `search(self, namespace: str, query: str) -> list[dict]`
- **`AgentDBBackend`**
  - `__init__(self, db_path: Optional[Path])`
  - `save_agent(self, agent_id: str, agent_type: str, status: str, capabilities: Optional[list], metadata: Optional[dict])`
  - `get_agent(self, agent_id: str) -> Optional[dict]`
  - `list_agents(self) -> list[dict]`

### `memory/faiss_index.py`

_FAISSIndex — HNSW vector index with SQLite metadata._

**Classes:**

- **`FAISSIndex`** — HNSW vector index with SQLite metadata store.
  - `__init__(self, index_path: str, dim: int) -> None`
  - `add(self, doc_id: str, vector: list[float], metadata: dict) -> None`
  - `search(self, query_vector: list[float], k: int, min_score: float) -> list[dict]`
  - `save(self) -> None`
  - `load(self) -> None`
  - `delete(self, doc_id: str) -> None`
  - `size(self) -> int`

### `memory/manager.py`

_MemoryManager — orchestrates VectorBuiltinMemoryProvider + at most one external provider._

**Classes:**

- **`MemoryManager`** — Orchestrates the built-in provider plus at most one external provider.
  - `__init__(self) -> None`
  - `add_provider(self, provider: MemoryProvider) -> None`
  - `providers(self) -> List[MemoryProvider]`
  - `get_provider(self, name: str) -> Optional[MemoryProvider]`
  - `build_system_prompt(self) -> str`
  - `prefetch_all(self, query: str, session_id: str) -> str`
  - `queue_prefetch_all(self, query: str, session_id: str) -> None`
  - `sync_all(self, user: str, assistant: str, session_id: str) -> None`
  - _(+11 more methods)_

**Functions:**

- `sanitize_context(text: str) -> str` — Strip fence tags, injected context blocks, and system notes from provider output.
- `build_memory_context_block(raw_context: str) -> str` — Wrap prefetched memory in a fenced block with system note.
- `get_memory_manager() -> MemoryManager` — Return the global MemoryManager singleton with VectorBuiltinMemoryProvider auto-loaded.
- `reset_memory_manager() -> None` — Reset the singleton (used in tests).

### `memory/pattern_store.py`

_PatternStore — SONA port for VectorCode._

**Classes:**

- **`PatternStore`** — Stores and retrieves task execution patterns using vector similarity.
  - `__init__(self, index_path: str, similarity_threshold: float) -> None`
  - `save_pattern(self, task: str, plan: list[str], outcome: str, reward: float) -> str`
  - `recall(self, task: str) -> dict | None`
  - `update_reward(self, pattern_id: str, reward: float) -> None`

### `memory/provider.py`

_MemoryProvider ABC + VectorBuiltinMemoryProvider — ported from reference memory_provider.py._

**Classes:**

- **`MemoryProvider`** — Abstract base class for pluggable memory providers.
  - `name(self) -> str`
  - `is_available(self) -> bool`
  - `initialize(self, session_id: str) -> None`
  - `system_prompt_block(self) -> str`
  - `prefetch(self, query: str, session_id: str) -> str`
  - `queue_prefetch(self, query: str, session_id: str) -> None`
  - `sync_turn(self, user_content: str, assistant_content: str, session_id: str) -> None`
  - `get_tool_schemas(self) -> List[Dict[str, Any]]`
  - _(+7 more methods)_
- **`VectorBuiltinMemoryProvider`** — Always-on provider that reads/writes ~/.vector/memory.md.
  - `name(self) -> str`
  - `is_available(self) -> bool`
  - `initialize(self, session_id: str) -> None`
  - `system_prompt_block(self) -> str`
  - `prefetch(self, query: str, session_id: str) -> str`
  - `sync_turn(self, user_content: str, assistant_content: str, session_id: str) -> None`
  - `get_tool_schemas(self) -> List[Dict[str, Any]]`
  - `on_session_end(self, messages: List[Dict[str, Any]]) -> None`

### `memory/swarm_db.py`

_SwarmDatabase — complete reference v2/src/hive-mind/storage/DatabaseManager.ts absorption._

**Classes:**

- **`SwarmDatabase`** — SQLite-backed persistent swarm storage.
  - `__init__(self, swarm_id: str)`
  - `save_agent_state(self, agent_id: str, data: dict) -> None`
  - `load_agent_state(self, agent_id: str) -> Optional[dict]`
  - `list_agents(self, status: Optional[str]) -> list[dict]`
  - `record_task(self, task_id: str, task_text: str, agent_id: str, domain: str, outcome: str, reward: float, latency_ms: float, started_at: Optional[float], metadata: Optional[dict]) -> None`
  - `get_task(self, task_id: str) -> Optional[dict]`
  - `get_agent_tasks(self, agent_id: str, limit: int) -> list[dict]`
  - `record_decision(self, decision_id: str, data: dict) -> None`
  - _(+5 more methods)_


---

## (root)

### `message_bus.py`

_MessageBus — Python port of reference v2/src/communication/message-bus.ts._

**Classes:**

- **`ChannelType`**
- **`QoS`**
- **`FilterOp`**
- **`FilterRule`** — A single ACL filter rule using one of 7 operators.
  - `evaluate(self, msg: 'Message') -> bool`
- **`ChannelACL`** — reference MessageBus ACL — allowedSenders, allowedReceivers, bannedAgents,
  - `can_publish(self, sender: str) -> bool`
  - `can_subscribe(self, subscriber_id: str) -> bool`
  - `passes_filters(self, msg: 'Message') -> bool`
  - `add_filter(self, field: str, op: FilterOp, value: object) -> None`
- **`Message`**
- **`ChannelStats`**
  - `success_rate(self) -> float`
- **`Channel`** — A named channel with ACL, subscriber management, QoS, and stats.
  - `__init__(self, name: str, channel_type: ChannelType, max_size: int, acl: Optional[ChannelACL])`
  - `subscribe(self, callback: Callable, subscriber_id: str) -> str | None`
  - `unsubscribe(self, subscriber_id: str) -> bool`
  - `publish(self, message: Message) -> int`
  - `acknowledge(self, message_id: str, subscriber_id: str) -> bool`
  - `get_dead_letters(self, limit: int) -> list`
  - `get_history(self, limit: int) -> list`
- **`MessageBus`** — Singleton in-process message broker with full reference ACL.
  - `get(cls) -> 'MessageBus'`
  - `__init__(self)`
  - `create_channel(self, name: str, channel_type: ChannelType, max_size: int, acl: Optional[ChannelACL]) -> Channel`
  - `set_acl(self, channel: str, acl: ChannelACL) -> None`
  - `get_channel(self, name: str) -> Channel | None`
  - `list_channels(self) -> list[str]`
  - `subscribe(self, channel: str, callback: Callable, subscriber_id: str) -> str | None`
  - `unsubscribe(self, channel: str, subscriber_id: str) -> bool`
  - _(+6 more methods)_


---

## migrations

### `migrations/v1_to_v10.py`

_Migration: session_db v1 → SCHEMA_VERSION 10._

**Functions:**

- `migrate_v1_to_v10(conn: sqlite3.Connection) -> None` — Apply all schema changes from v1 to v10 in-place.
- `migrate_up(db_path: Path) -> None` — Migrate the database at db_path to the latest schema version.


---

## (root)

### `mini_swe_runner.py`

_SWE Runner with VectorCode Trajectory Format_

**Classes:**

- **`MiniSWERunner`** — Agent runner that uses VectorCode's built-in execution environments
  - `__init__(self, model: str, base_url: str, api_key: str, env_type: str, image: str, cwd: str, max_iterations: int, command_timeout: int, verbose: bool)`
  - `run_task(self, task: str) -> Dict[str, Any]`
  - `run_batch(self, prompts: List[str], output_file: str) -> List[Dict[str, Any]]`

**Functions:**

- `create_environment(env_type: str, image: str, cwd: str, timeout: int)` — Create an execution environment using VectorCode's built-in backends.
- `main(task: str, prompts_file: str, output_file: str, model: str, base_url: str, api_key: str, env: str, image: str, cwd: str, max_iterations: int, timeout: int, verbose: bool)` — Run SWE tasks with VectorCode trajectory format output.


---

## (root)

### `model_tools.py`

_Model Tools Module_

**Functions:**

- `get_tool_definitions(enabled_toolsets: List[str], disabled_toolsets: List[str], quiet_mode: bool) -> List[Dict[str, Any]]` — Get tool definitions for model API calls with toolset-based filtering.
- `coerce_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]` — Coerce tool call arguments to match their JSON Schema types.
- `handle_function_call(function_name: str, function_args: Dict[str, Any], task_id: Optional[str], tool_call_id: Optional[str], session_id: Optional[str], user_task: Optional[str], enabled_tools: Optional[List[str]], skip_pre_tool_call_hook: bool) -> str` — Main function call dispatcher that routes calls to the tool registry.
- `get_all_tool_names() -> List[str]` — Return all registered tool names.
- `get_toolset_for_tool(tool_name: str) -> Optional[str]` — Return the toolset a tool belongs to.
- `get_available_toolsets() -> Dict[str, dict]` — Return toolset availability info for UI display.
- `check_toolset_requirements() -> Dict[str, bool]` — Return {toolset: available_bool} for every registered toolset.
- `check_tool_availability(quiet: bool) -> Tuple[List[str], List[dict]]` — Return (available_toolsets, unavailable_info).


---

## (root)

### `monitoring.py`

_SwarmMonitor — complete reference real-time-monitor.ts + health-check.ts + diagnostics.ts absorption._

**Classes:**

- **`AgentMetric`**
- **`SwarmSnapshot`** — Point-in-time swarm state — reference real-time-monitor snapshot.
- **`HealthStatus`**
- **`HealthReport`** — reference health-check.ts output — per-component status.
- **`DiagnosticsReport`** — reference diagnostics.ts output — deeper system analysis.
- **`SwarmMonitor`** — Real-time swarm health monitoring absorbed from reference's monitoring/ module.
  - `__init__(self)`
  - `take_snapshot(self, swarm: 'SwarmCoordinator') -> SwarmSnapshot`
  - `run_health_check(self, swarm: 'SwarmCoordinator', bus: Optional['MessageBus']) -> HealthReport`
  - `run_diagnostics(self, swarm: 'SwarmCoordinator', bus: Optional['MessageBus']) -> DiagnosticsReport`
  - `get_metrics(self, window_seconds: float) -> dict`
  - `snapshot_history(self, limit: int) -> list[dict]`


---

## persona

### `persona/person_model.py`

_PersonModel — absorbed from reference communications/person_model.py._

**Classes:**

- **`PersonModel`** — Learns communication style profiles from message history.
  - `__init__(self)`
  - `learn_from_messages(self, person_name: str, messages: list[dict]) -> dict`
  - `get_style(self, person_name: str) -> dict`
  - `generate_response_style(self, person_name: str, text: str) -> str`
  - `list_profiles(self) -> list[str]`
  - `delete_profile(self, person_name: str) -> bool`
  - `compare_with(self, person_a: str, person_b: str) -> dict`

### `persona/personalities.py`

_Personality system — loadable profile overrides for the system prompt._

**Functions:**

- `get_personality(name: str) -> Optional[dict]` — Get a personality by name. Falls back to 'default' if not found.
- `list_personalities() -> list[str]` — Return sorted list of available personality names.
- `build_personality_prompt(name: str) -> str` — Build the system prompt overrides for a personality.

### `persona/style_model.py`

_StyleModel — absorbed from reference communications/style_model.py._

**Classes:**

- **`StyleModel`** — Analyzes conversation style and adjusts tone/formality via Ollama.
  - `__init__(self)`
  - `analyze_conversation(self, messages: list[dict]) -> dict`
  - `suggest_tone_adjustment(self, text: str, target_tone: str) -> str`
  - `match_formality_level(self, text: str, level: str) -> str`
  - `compare_styles(self, messages_a: list[dict], messages_b: list[dict]) -> dict`


---

## plugins

### `plugins/agentic_qe.py`

_Agentic QE Plugin — test generation, security scanning, quality assessment._

**Classes:**

- **`AgenticQEPlugin`**
  - `__init__(self)`

### `plugins/bridges/cognitive_bridge.py`

_Cognitive Bridge — working memory, attention control, meta-cognition._

**Classes:**

- **`CognitiveBridge`**
  - `__init__(self, capacity: int)`
  - `store(self, items: list) -> dict`
  - `recall(self, query: str) -> list`
  - `focus_attention(self, target: str) -> dict`
  - `diff_attention(self) -> dict`
  - `meta_assess(self) -> dict`

### `plugins/bridges/gnn_bridge.py`

_GNN Bridge — code graph analysis using numpy-based graph algorithms._

**Classes:**

- **`GNNBridge`**
  - `__init__(self, dim: int)`
  - `build_graph(self, nodes: list[dict], edges: list[tuple[str, str]]) -> dict`
  - `compute_embeddings(self, nodes: list[str], adj_matrix: Optional[list]) -> dict[str, list[float]]`
  - `predict_impact(self, changed_node: str, graph: dict) -> list[dict]`
  - `detect_communities(self, adj_matrix: list[list[float]]) -> list[list[int]]`
  - `match_patterns(self, code_graph: dict, patterns: list[dict]) -> list[dict]`

### `plugins/bridges/mincut_bridge.py`

_MinCut Bridge — graph partitioning for module boundary detection._

**Classes:**

- **`MinCutBridge`**
  - `partition(self, adj_matrix: list[list[float]], k: int) -> list[list[int]]`
  - `detect_boundaries(self, files: list[str], dependencies: list[tuple[str, str]]) -> list[dict]`

### `plugins/bridges/qe_core_bridge.py`

_QE Core Bridge — ACL for V3 core services (Agent, Task, Workflow, Config)._

**Classes:**

- **`QECoreBridge`**
  - `__init__(self)`
  - `get_agent(self, agent_id: str) -> Optional[dict]`
  - `create_task(self, task_def: dict) -> dict`
  - `execute_workflow(self, steps: list) -> dict`

### `plugins/bridges/qe_hive_bridge.py`

_QE Hive Bridge — ACL for V3 Hive-Mind coordination._

**Classes:**

- **`QEHiveBridge`**
  - `register_agent(self, agent_type: str, capabilities: list) -> dict`
  - `consensus_vote(self, proposal: dict, votes: list) -> dict`

### `plugins/bridges/qe_memory_bridge.py`

_QE Memory Bridge — ACL for V3 memory system._

**Classes:**

- **`QEMemoryBridge`**
  - `store_pattern(self, pattern: dict) -> dict`
  - `search_patterns(self, query: str, limit: int) -> list`
  - `get_coverage(self, namespace: str) -> dict`

### `plugins/bridges/qe_model_routing.py`

_QE Model Routing Adapter — 3-tier model routing._

**Classes:**

- **`QEModelRoutingAdapter`**
  - `route(self, task: str, complexity: str) -> str`

### `plugins/bridges/qe_security_bridge.py`

_QE Security Bridge — ACL for V3 security (path validation, safe exec)._

**Classes:**

- **`QESecurityBridge`**
  - `__init__(self, allowed_paths: Optional[list[str]])`
  - `validate_path(self, path: str) -> bool`
  - `validate_command(self, command: str) -> bool`

### `plugins/bridges/sona_bridge.py`

_SONA Bridge — Self-Optimizing Neural Architecture (LoRA fine-tuning, EWC++)._

**Classes:**

- **`SonaBridge`**
  - `__init__(self)`
  - `fine_tune(self, examples: list, mode: str) -> dict`
  - `learn_continuous(self, pattern: dict) -> dict`
  - `set_mode(self, mode: str) -> dict`

### `plugins/code_intelligence.py`

_Code Intelligence Plugin — GNN-based code analysis and semantic search._

**Classes:**

- **`CodeIntelligencePlugin`**
  - `__init__(self)`

### `plugins/cognitive_kernel.py`

_Cognitive Kernel Plugin — working memory, attention control, meta-cognition._

**Classes:**

- **`CognitiveKernelPlugin`**
  - `__init__(self)`

### `plugins/disk-cleanup/disk_cleanup.py`

_disk_cleanup — ephemeral file cleanup for VectorCode._

**Functions:**

- `get_state_dir() -> Path` — State dir — separate from ``$VECTOR_HOME/logs/``.
- `get_tracked_file() -> Path`
- `get_log_file() -> Path` — Audit log — intentionally NOT under ``$VECTOR_HOME/logs/``.
- `is_safe_path(path: Path) -> bool` — Accept only paths under VECTOR_HOME or ``/tmp/vector-*``.
- `load_tracked() -> List[Dict[str, Any]]` — Load tracked.json.  Restores from ``.bak`` on corruption.
- `save_tracked(tracked: List[Dict[str, Any]]) -> None` — Atomic write: ``.tmp`` → backup old → rename.
- `fmt_size(n: float) -> str`
- `track(path_str: str, category: str, silent: bool) -> bool` — Register a file for tracking. Returns True if newly tracked.
- `forget(path_str: str) -> int` — Remove a path from tracking without deleting the file.
- `dry_run() -> Tuple[List[Dict], List[Dict]]` — Return (auto_delete_list, needs_prompt_list) without touching files.
- `quick() -> Dict[str, Any]` — Safe deterministic cleanup — no prompts.
- `deep(confirm: Optional[callable]) -> Dict[str, Any]` — Deep cleanup.
- `status() -> Dict[str, Any]` — Return per-category breakdown and top 10 largest tracked files.
- `format_status(s: Dict[str, Any]) -> str` — Human-readable status string (for slash command output).
- `guess_category(path: Path) -> Optional[str]` — Return a category label for *path*, or None if we shouldn't track it.

### `plugins/disk_cleanup_plugin.py`

_Disk cleanup plugin — free space by removing cache and temp files._

**Functions:**

- `get_size(path: Path) -> int`
- `clean(confirm: bool) -> dict`

### `plugins/example-dashboard/dashboard/plugin_api.py`

_Example dashboard plugin — backend API routes._

**Functions:**

- `hello()` — Simple greeting endpoint to demonstrate plugin API routes.

### `plugins/financial_risk.py`

_Financial Risk Analysis Plugin — portfolio risk, anomaly detection, compliance._

**Classes:**

- **`FinancialRiskPlugin`**
  - `__init__(self)`

### `plugins/google_meet/audio_bridge.py`

_Virtual audio bridge for feeding generated speech into Chrome's mic._

**Classes:**

- **`AudioBridge`** — Manages a virtual audio device for Chrome fake-mic input.
  - `__init__(self, name_prefix: str) -> None`
  - `device_name(self) -> str`
  - `write_target(self) -> str`
  - `setup(self) -> dict`
  - `teardown(self) -> None`

**Functions:**

- `chrome_fake_audio_flags(bridge_info: dict) -> list[str]` — Return Chrome flags for using the fake audio input.

### `plugins/google_meet/cli.py`

_CLI commands for the google_meet plugin._

**Functions:**

- `register_cli(subparser: argparse.ArgumentParser) -> None` — Build the ``vector meet`` argparse tree.
- `meet_command(args: argparse.Namespace) -> int`

### `plugins/google_meet/meet_bot.py`

_Headless Google Meet bot — Playwright + live-caption scraping._

**Functions:**

- `run_bot() -> int`

### `plugins/google_meet/node/cli.py`

_`vector meet node ...` subcommand tree._

**Functions:**

- `register_cli(subparser: argparse.ArgumentParser) -> None` — Add ``run / list / approve / remove / status / ping`` subparsers.
- `node_command(args: argparse.Namespace) -> int` — Dispatch for ``vector meet node ...``.

### `plugins/google_meet/node/client.py`

_Gateway-side RPC client for a remote meet node._

**Classes:**

- **`NodeClient`** — Thin synchronous WS client matching the server's request surface.
  - `__init__(self, url: str, token: str, timeout: float) -> None`
  - `start_bot(self, url: str, guest_name: str, duration: Optional[str], headed: bool, mode: str) -> Dict[str, Any]`
  - `stop(self) -> Dict[str, Any]`
  - `status(self) -> Dict[str, Any]`
  - `transcript(self, last: Optional[int]) -> Dict[str, Any]`
  - `say(self, text: str) -> Dict[str, Any]`
  - `ping(self) -> Dict[str, Any]`

### `plugins/google_meet/node/protocol.py`

_Wire protocol for gateway ↔ node RPC._

**Functions:**

- `make_request(type: str, token: str, payload: Dict[str, Any], req_id: str | None) -> Dict[str, Any]` — Construct a request envelope.
- `make_response(req_id: str, payload: Dict[str, Any]) -> Dict[str, Any]` — Build a success response. The caller supplies the *request* type;
- `make_error(req_id: str, error: str) -> Dict[str, Any]`
- `encode(msg: Dict[str, Any]) -> str` — Serialize a message envelope to a JSON string.
- `decode(raw: str) -> Dict[str, Any]` — Parse a JSON envelope, raising ValueError on anything malformed.
- `validate_request(msg: Dict[str, Any], expected_token: str) -> Tuple[bool, str]` — Check a decoded request against the server's shared token.

### `plugins/google_meet/node/registry.py`

_Local JSON registry of approved remote meet nodes._

**Classes:**

- **`NodeRegistry`** — Simple file-backed registry. Not concurrent-safe across processes
  - `__init__(self, path: Optional[Path]) -> None`
  - `get(self, name: str) -> Optional[Dict[str, Any]]`
  - `add(self, name: str, url: str, token: str) -> None`
  - `remove(self, name: str) -> bool`
  - `list_all(self) -> List[Dict[str, Any]]`
  - `resolve(self, chrome_node: Optional[str]) -> Optional[Dict[str, Any]]`

### `plugins/google_meet/node/server.py`

_Remote node server._

**Classes:**

- **`NodeServer`** — WebSocket server that executes meet bot RPCs locally.
  - `__init__(self, host: str, port: int, token_path: Optional[Path], display_name: str) -> None`
  - `ensure_token(self) -> str`
  - `get_token(self) -> str`
  - `serve(self) -> None`

### `plugins/google_meet/process_manager.py`

_Subprocess lifecycle manager for the google_meet bot._

**Functions:**

- `start(url: str, out_dir: Optional[Path], headed: bool, auth_state: Optional[str], guest_name: str, duration: Optional[str], session_id: Optional[str], mode: str, realtime_model: Optional[str], realtime_voice: Optional[str], realtime_instructions: Optional[str], realtime_api_key: Optional[str]) -> Dict[str, Any]` — Spawn the meet_bot subprocess for *url*.
- `status() -> Dict[str, Any]` — Return the current meeting state, or ``{"ok": False, "reason": ...}``.
- `transcript(last: Optional[int]) -> Dict[str, Any]` — Read the current transcript file. Returns ok=False if none exists.
- `enqueue_say(text: str) -> Dict[str, Any]` — Append a ``say`` request to the active bot's JSONL queue.
- `stop(reason: str) -> Dict[str, Any]` — Signal the active bot to leave cleanly, then clear the active pointer.

### `plugins/google_meet/realtime/openai_client.py`

_OpenAI Realtime API WebSocket client + file-queue speaker._

**Classes:**

- **`RealtimeSession`** — Minimal sync client for the OpenAI Realtime WebSocket API.
  - `__init__(self, api_key: str, model: str, voice: str, instructions: str, audio_sink_path: Optional[Path], sample_rate: int) -> None`
  - `connect(self) -> None`
  - `close(self) -> None`
  - `speak(self, text: str, timeout: float) -> dict`
  - `cancel_response(self) -> bool`
- **`RealtimeSpeaker`** — File-based JSONL queue wrapper around :class:`RealtimeSession`.
  - `__init__(self, session: RealtimeSession, queue_path: Path, processed_path: Optional[Path]) -> None`
  - `run_until_stopped(self, stop_fn: Callable[[], bool], poll_interval: float) -> None`

### `plugins/google_meet/tools.py`

_Agent-facing tools for the google_meet plugin._

**Functions:**

- `check_meet_requirements() -> bool` — Return True when the plugin can actually run LOCALLY.
- `handle_meet_join(args: Dict[str, Any]) -> str`
- `handle_meet_status(args: Dict[str, Any]) -> str`
- `handle_meet_transcript(args: Dict[str, Any]) -> str`
- `handle_meet_leave(args: Dict[str, Any]) -> str`
- `handle_meet_say(args: Dict[str, Any]) -> str`

### `plugins/google_meet_plugin.py`

_Google Meet plugin — audio bridge, bot, process management._

**Classes:**

- **`GoogleMeetPlugin`**
  - `__init__(self)`
  - `join_meeting(self, meeting_url: str, audio_only: bool) -> dict`
  - `leave_meeting(self) -> dict`
  - `get_audio_feed(self) -> Optional[str]`
  - `status(self) -> dict`

### `plugins/healthcare_clinical.py`

_Healthcare Clinical Plugin — patient risk, clinical decision support._

**Classes:**

- **`HealthcareClinicalPlugin`**
  - `__init__(self)`

### `plugins/hyperbolic_reasoning.py`

_Hyperbolic Reasoning Plugin — hyperbolic geometry for hierarchical embeddings._

**Classes:**

- **`HyperbolicReasoningPlugin`**
  - `__init__(self)`

### `plugins/image_gen_plugins.py`

_Image generation provider plugins — OpenAI, Codex, xAI backends._

**Functions:**

- `generate_openai(prompt: str, size: str, n: int) -> dict`
- `generate_codex(prompt: str, size: str) -> dict`
- `generate_xai(prompt: str) -> dict`

### `plugins/legal_contracts.py`

_Legal Contracts Plugin — contract analysis, clause extraction, compliance._

**Classes:**

- **`LegalContractsPlugin`**
  - `__init__(self)`

### `plugins/loader.py`

_Plugin discovery and loading for VectorCode._

**Functions:**

- `discover_plugins(extra_dirs: Optional[List[Path]]) -> List[Path]` — Return list of plugin directories found in all plugin search paths.
- `load_plugin(plugin_path: Path) -> Optional[Any]` — Load a plugin from a directory (with plugin.toml) or a .py file.
- `activate_plugin(plugin_mod: Any, engine: Any) -> None` — Call plugin's activate() if it exists, passing the engine.

### `plugins/memory/holographic/holographic.py`

_Holographic Reduced Representations (HRR) with phase encoding._

**Functions:**

- `encode_atom(word: str, dim: int) -> 'np.ndarray'` — Deterministic phase vector via SHA-256 counter blocks.
- `bind(a: 'np.ndarray', b: 'np.ndarray') -> 'np.ndarray'` — Circular convolution = element-wise phase addition.
- `unbind(memory: 'np.ndarray', key: 'np.ndarray') -> 'np.ndarray'` — Circular correlation = element-wise phase subtraction.
- `bundle() -> 'np.ndarray'` — Superposition via circular mean of complex exponentials.
- `similarity(a: 'np.ndarray', b: 'np.ndarray') -> float` — Phase cosine similarity. Range [-1, 1].
- `encode_text(text: str, dim: int) -> 'np.ndarray'` — Bag-of-words: bundle of atom vectors for each token.
- `encode_fact(content: str, entities: list[str], dim: int) -> 'np.ndarray'` — Structured encoding: content bound to ROLE_CONTENT, each entity bound to ROLE_ENTITY, all bundled.
- `phases_to_bytes(phases: 'np.ndarray') -> bytes` — Serialize phase vector to bytes. float64 tobytes — 8 KB at dim=1024.
- `bytes_to_phases(data: bytes) -> 'np.ndarray'` — Deserialize bytes back to phase vector. Inverse of phases_to_bytes.
- `snr_estimate(dim: int, n_items: int) -> float` — Signal-to-noise ratio estimate for holographic storage.

### `plugins/memory/holographic/retrieval.py`

_Hybrid keyword/BM25 retrieval for the memory store._

**Classes:**

- **`FactRetriever`** — Multi-strategy fact retrieval with trust-weighted scoring.
  - `__init__(self, store: MemoryStore, temporal_decay_half_life: int, fts_weight: float, jaccard_weight: float, hrr_weight: float, hrr_dim: int)`
  - `search(self, query: str, category: str | None, min_trust: float, limit: int) -> list[dict]`
  - `probe(self, entity: str, category: str | None, limit: int) -> list[dict]`
  - `related(self, entity: str, category: str | None, limit: int) -> list[dict]`
  - `reason(self, entities: list[str], category: str | None, limit: int) -> list[dict]`
  - `contradict(self, category: str | None, threshold: float, limit: int) -> list[dict]`

### `plugins/memory/holographic/store.py`

_SQLite-backed fact store with entity resolution and trust scoring._

**Classes:**

- **`MemoryStore`** — SQLite-backed fact store with entity resolution and trust scoring.
  - `__init__(self, db_path: 'str | Path | None', default_trust: float, hrr_dim: int) -> None`
  - `add_fact(self, content: str, category: str, tags: str) -> int`
  - `search_facts(self, query: str, category: str | None, min_trust: float, limit: int) -> list[dict]`
  - `update_fact(self, fact_id: int, content: str | None, trust_delta: float | None, tags: str | None, category: str | None) -> bool`
  - `remove_fact(self, fact_id: int) -> bool`
  - `list_facts(self, category: str | None, min_trust: float, limit: int) -> list[dict]`
  - `record_feedback(self, fact_id: int, helpful: bool) -> dict`
  - `rebuild_all_vectors(self, dim: int | None) -> int`
  - _(+1 more methods)_

### `plugins/memory/honcho/cli.py`

_CLI commands for Honcho integration management._

**Functions:**

- `clone_honcho_for_profile(profile_name: str) -> bool` — Auto-clone Honcho config for a new profile from the default host block.
- `cmd_enable(args) -> None` — Enable Honcho for the active profile.
- `cmd_disable(args) -> None` — Disable Honcho for the active profile.
- `cmd_sync(args) -> None` — Sync Honcho config to all existing profiles.
- `sync_honcho_profiles_quiet() -> int` — Sync Honcho host blocks for all profiles. Returns count of newly created blocks.
- `cmd_setup(args) -> None` — Interactive Honcho setup wizard.
- `cmd_status(args) -> None` — Show current Honcho config and connection status.
- `cmd_peers(args) -> None` — Show peer identities across all profiles.
- `cmd_sessions(args) -> None` — List known directory → session name mappings.
- `cmd_map(args) -> None` — Map current directory to a Honcho session name.
- `cmd_peer(args) -> None` — Show or update peer names and dialectic reasoning level.
- `cmd_mode(args) -> None` — Show or set the recall mode.
- `cmd_strategy(args) -> None` — Show or set the session strategy.
- `cmd_tokens(args) -> None` — Show or set token budget settings.
- `cmd_identity(args) -> None` — Seed AI peer identity or show both peer representations.
- _(+3 more functions)_

### `plugins/memory/honcho/client.py`

_Honcho client initialization and configuration._

**Classes:**

- **`HonchoClientConfig`** — Configuration for Honcho client, resolved for a specific host.
  - `from_env(cls, workspace_id: str, host: str | None) -> HonchoClientConfig`
  - `from_global_config(cls, host: str | None, config_path: Path | None) -> HonchoClientConfig`
  - `resolve_session_name(self, cwd: str | None, session_title: str | None, session_id: str | None, gateway_session_key: str | None) -> str | None`

**Functions:**

- `resolve_active_host() -> str` — Derive the Honcho host key from the active VectorCode profile.
- `resolve_global_config_path() -> Path` — Return the shared Honcho config path for the current HOME.
- `resolve_config_path() -> Path` — Return the active Honcho config path.
- `get_honcho_client(config: HonchoClientConfig | None) -> Honcho` — Get or create the Honcho client singleton.
- `reset_honcho_client() -> None` — Reset the Honcho client singleton (useful for testing).

### `plugins/memory/honcho/session.py`

_Honcho-based session management for conversation history._

**Classes:**

- **`HonchoSession`** — A conversation session backed by Honcho.
  - `add_message(self, role: str, content: str) -> None`
  - `get_history(self, max_messages: int) -> list[dict[str, Any]]`
  - `clear(self) -> None`
- **`HonchoSessionManager`** — Manages conversation sessions using Honcho.
  - `__init__(self, honcho: Honcho | None, context_tokens: int | None, config: Any | None, runtime_user_peer_name: str | None)`
  - `honcho(self) -> Honcho`
  - `get_or_create(self, key: str) -> HonchoSession`
  - `save(self, session: HonchoSession) -> None`
  - `flush_all(self) -> None`
  - `shutdown(self) -> None`
  - `delete(self, key: str) -> bool`
  - `new_session(self, key: str) -> HonchoSession`
  - _(+16 more methods)_

### `plugins/memory_plugins/mem0_plugin.py`

_Mem0 memory plugin — LLM fact extraction via Mem0 Platform API._

**Classes:**

- **`Mem0Plugin`**
  - `__init__(self)`
  - `initialize(self)`
  - `add(self, messages: list[dict]) -> dict`
  - `search(self, query: str, limit: int) -> list`
  - `get_history(self) -> list`

### `plugins/memory_plugins/memory_backends.py`

_Memory backend plugins — Byterover, Hindsight, Holographic, Honcho, OpenViking, RetainDB, Supermemory._

**Classes:**

- **`ByteroverPlugin`**
  - `store(self, key: str, value: Any) -> dict`
  - `retrieve(self, key: str) -> Optional[Any]`
- **`HindsightPlugin`**
  - `store(self, key: str, value: Any) -> dict`
  - `retrieve(self, key: str) -> Optional[Any]`
- **`HolographicPlugin`**
  - `__init__(self, dim: int)`
  - `store(self, key: str, vector: list[float], metadata: Optional[dict]) -> dict`
  - `retrieve(self, key: str) -> Optional[dict]`
  - `search(self, query_vector: list[float], k: int) -> list`
- **`HonchoPlugin`**
  - `__init__(self, base_url: str)`
  - `create_session(self, user_id: str) -> dict`
  - `list_sessions(self, user_id: str) -> list`
- **`OpenVikingPlugin`**
  - `query(self, query: str, collection: str) -> list`
- **`RetainDBPlugin`**
  - `__init__(self, ttl_days: int)`
  - `store(self, key: str, value: Any) -> dict`
  - `retrieve(self, key: str) -> Optional[Any]`
- **`SupermemoryPlugin`**
  - `store(self, key: str, value: Any) -> dict`
  - `search(self, query: str) -> list`

### `plugins/neural_coordination.py`

_Neural Coordination Plugin — nervous-system-inspired agent coordination._

**Classes:**

- **`NeuralCoordinationPlugin`**
  - `__init__(self)`

### `plugins/perf_optimizer.py`

_Performance Optimizer Plugin — benchmarks, profiling, optimization._

**Classes:**

- **`PerfOptimizerPlugin`**
  - `__init__(self)`

### `plugins/plugin.py`

_VectorCode v3 Plugin — core contract for extensible capabilities._

**Classes:**

- **`ExtensionPoint`** — A point where plugins can extend system behavior.
  - `__init__(self, name: str, description: str)`
  - `register(self, handler: Callable)`
  - `execute(self) -> list[Any]`
- **`Plugin`**
  - `__init__(self, plugin_id: str, name: str, version: str, description: str, dependencies: Optional[list[str]])`
  - `register_extension(self, point: ExtensionPoint)`
  - `get_extension(self, name: str) -> Optional[ExtensionPoint]`
  - `list_extensions(self) -> list[str]`
  - `initialize(self, config: Optional[dict])`
  - `shutdown(self)`
- **`PluginManager`**
  - `__init__(self)`
  - `register(self, plugin: Plugin)`
  - `get(self, plugin_id: str) -> Optional[Plugin]`
  - `list(self) -> list[Plugin]`
  - `get_extension(self, name: str) -> Optional[ExtensionPoint]`
  - `initialize_all(self, configs: Optional[dict[str, dict]])`
  - `shutdown_all(self)`

### `plugins/prime_radiant.py`

_Prime Radiant Plugin — causal, cohomology, quantum, spectral engines._

**Classes:**

- **`PrimeRadiantPlugin`**
  - `__init__(self)`

### `plugins/quantum_optimizer.py`

_Quantum Optimizer Plugin — quantum-inspired optimization algorithms._

**Classes:**

- **`QuantumOptimizerPlugin`**
  - `__init__(self)`

### `plugins/ruvector_upstream.py`

_Ruvector Upstream Plugin — upstream bridge integrations._

**Classes:**

- **`RuvectorUpstreamPlugin`**
  - `__init__(self)`

### `plugins/spotify/client.py`

_Thin Spotify Web API helper used by VectorCode native tools._

**Classes:**

- **`SpotifyError`** — Base Spotify tool error.
- **`SpotifyAuthRequiredError`** — Raised when the user needs to authenticate with Spotify first.
- **`SpotifyAPIError`** — Structured Spotify API failure.
  - `__init__(self, message: str, status_code: Optional[int], response_body: Optional[str]) -> None`
- **`SpotifyClient`**
  - `__init__(self) -> None`
  - `base_url(self) -> str`
  - `request(self, method: str, path: str, params: Optional[Dict[str, Any]], json_body: Optional[Dict[str, Any]], allow_retry_on_401: bool, empty_response: Optional[Dict[str, Any]]) -> Any`
  - `get_devices(self) -> Any`
  - `transfer_playback(self, device_id: str, play: bool) -> Any`
  - `get_playback_state(self, market: Optional[str]) -> Any`
  - `get_currently_playing(self, market: Optional[str]) -> Any`
  - `start_playback(self, device_id: Optional[str], context_uri: Optional[str], uris: Optional[list[str]], offset: Optional[Dict[str, Any]], position_ms: Optional[int]) -> Any`
  - _(+25 more methods)_

**Functions:**

- `normalize_spotify_id(value: str, expected_type: Optional[str]) -> str`
- `normalize_spotify_uri(value: str, expected_type: Optional[str]) -> str`
- `normalize_spotify_uris(values: Iterable[str], expected_type: Optional[str]) -> list[str]`
- `compact_json(data: Any) -> str`

### `plugins/spotify/tools.py`

_Native Spotify tools for VectorCode (registered via plugins/spotify)._

### `plugins/spotify_plugin.py`

_Spotify plugin — control playback, search, manage playlists._

**Classes:**

- **`SpotifyPlugin`**
  - `__init__(self, client_id: str, client_secret: str, redirect_uri: str)`
  - `initialize(self)`
  - `current_track(self) -> dict`
  - `search(self, query: str, limit: int) -> list`
  - `play(self, uri: str) -> dict`
  - `pause(self) -> dict`

### `plugins/teammate_plugin.py`

_Teammate Plugin — topology optimization, multi-agent routing._

**Classes:**

- **`TeammatePlugin`**
  - `__init__(self)`

### `plugins/test_intelligence.py`

_Test Intelligence Plugin — test generation, coverage analysis, defect prediction._

**Classes:**

- **`TestIntelligencePlugin`**
  - `__init__(self)`


---

## providers

### `providers/base.py`

_Base provider interface and shared types for VectorCode._

**Classes:**

- **`TokenUsage`**
- **`ToolCall`**
- **`Message`**
- **`ModelCapabilities`**
- **`CompletionResult`**
- **`BaseProvider`** — All VectorCode provider adapters must implement this interface.
  - `complete(self, model: str, messages: list[dict], tools: list[dict] | None, stream: bool, max_tokens: int) -> CompletionResult`
  - `probe_capabilities(self, model: str) -> ModelCapabilities`

**Functions:**

- `estimate_cost(model: str, usage: TokenUsage) -> float` — Return estimated cost in USD for a completion. Returns 0.0 for local models.

### `providers/capability_probe.py`

_Capability probing for VectorCode providers._

**Classes:**

- **`CapabilityProbe`** — Probe a model once; cache the result; re-use on subsequent calls.
  - `__init__(self) -> None`
  - `get_or_probe(self, model_id: str, provider) -> ModelCapabilities`

**Functions:**

- `strip_provider_prefix(model_id: str) -> str` — Strip a recognized provider prefix from a model string.
- `get_context_length(model_id: str, default: int) -> int` — Return context window size for a model.

### `providers/error_classifier.py`

_API error classification for smart failover and recovery._

**Classes:**

- **`FailoverReason`**
- **`ClassifiedError`**
  - `is_auth(self) -> bool`

**Functions:**

- `classify_api_error(error: Exception, provider: str, model: str, approx_tokens: int, context_length: int, num_messages: int) -> ClassifiedError`

### `providers/model_metadata.py`

_Model metadata — registry of model capabilities and pricing._

**Functions:**

- `get_model_info(model_id: str) -> Optional[dict]`
- `get_context_length(model_id: str) -> int`
- `get_pricing(model_id: str) -> dict`
- `estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float`

### `providers/ollama.py`

_Ollama provider adapter._

**Classes:**

- **`OllamaProvider`** — Ollama local model provider — OpenAI-compat REST at localhost:11434.
  - `__init__(self, base_url: str) -> None`
  - `complete(self, model: str, messages: list[dict], tools: list[dict] | None, stream: bool, max_tokens: int) -> CompletionResult`
  - `probe_capabilities(self, model: str) -> ModelCapabilities`

### `providers/openai_compat.py`

_Generic OpenAI-compatible provider adapter._

**Classes:**

- **`OpenAICompatProvider`** — Provider for any OpenAI-compatible REST endpoint.
  - `__init__(self, base_url: str, api_key: str, api_key_env: str) -> None`
  - `complete(self, model: str, messages: list[dict], tools: list[dict] | None, stream: bool, max_tokens: int) -> CompletionResult`
  - `probe_capabilities(self, model: str) -> ModelCapabilities`
- **`AnthropicProvider`** — Anthropic Claude provider using the anthropic SDK.
  - `__init__(self, api_key: str, api_key_env: str) -> None`
  - `complete(self, model: str, messages: list[dict], tools: list[dict] | None, stream: bool, max_tokens: int) -> CompletionResult`
  - `probe_capabilities(self, model: str) -> ModelCapabilities`
- **`GoogleProvider`** — Google Gemini provider using google-generativeai SDK.
  - `__init__(self, api_key: str, api_key_env: str) -> None`
  - `complete(self, model: str, messages: list[dict], tools: list[dict] | None, stream: bool, max_tokens: int) -> CompletionResult`
  - `probe_capabilities(self, model: str) -> ModelCapabilities`
- **`GroqProvider`**
  - `__init__(self, api_key: str, api_key_env: str) -> None`
- **`MistralProvider`**
  - `__init__(self, api_key: str, api_key_env: str) -> None`
- **`OpenAIProvider`**
  - `__init__(self, api_key: str, api_key_env: str) -> None`
- **`DeepSeekProvider`**
  - `__init__(self, api_key: str, api_key_env: str) -> None`
- **`OpenRouterProvider`**
  - `__init__(self, api_key: str, api_key_env: str) -> None`
- **`LMStudioProvider`** — LM Studio local server (default port 1234).
  - `__init__(self, base_url: str) -> None`

### `providers/prompt_caching.py`

_Prompt caching — Anthropic cache_control breakpoint management._

**Classes:**

- **`PromptCacheManager`** — Manages cache_control breakpoints for Anthropic prompt caching.
  - `estimate_tokens(self, content) -> int`
  - `should_cache_system(self, system: Union[str, list]) -> bool`
  - `should_cache_tools(self, tools: list[dict]) -> bool`
  - `apply_cache_control(self, system: Union[str, list, None], tools: Union[list[dict], None], messages: list[dict]) -> tuple[Union[str, list, None], Union[list[dict], None], list[dict]]`
  - `strip_cache_control(self, messages: list[dict]) -> list[dict]`

**Functions:**

- `get_prompt_cache_manager() -> PromptCacheManager` — Return the module-level singleton PromptCacheManager.

### `providers/rate_limit.py`

_Rate limit tracking — absorbed from reference agent/rate_limit_tracker.py._

**Classes:**

- **`RateLimitBucket`** — One rate-limit window (requests/min, tokens/min, etc.).
  - `used(self) -> int`
  - `usage_pct(self) -> float`
  - `remaining_seconds_now(self) -> float`
- **`RateLimitState`** — Full rate-limit state for one provider/request.
  - `has_data(self) -> bool`
  - `age_seconds(self) -> float`

**Functions:**

- `parse_rate_limit_headers(headers: Mapping[str, str], provider: str) -> Optional[RateLimitState]` — Parse x-ratelimit-* headers into a RateLimitState. Returns None if absent.
- `format_rate_limits(state: RateLimitState) -> str` — Full rate-limit display for /usage command.
- `format_rate_limits_compact(state: RateLimitState) -> str`

### `providers/rate_limit_tracker.py`

_Rate limit tracking for inference API responses._

**Classes:**

- **`RateLimitBucket`**
  - `used(self) -> int`
  - `usage_pct(self) -> float`
  - `remaining_seconds_now(self) -> float`
- **`RateLimitState`**
  - `has_data(self) -> bool`
  - `age_seconds(self) -> float`

**Functions:**

- `parse_rate_limit_headers(headers: Mapping[str, str], provider: str) -> Optional[RateLimitState]`
- `format_rate_limit_display(state: RateLimitState) -> str`

### `providers/retry.py`

_Jittered backoff — absorbed from reference agent/retry_utils.py._

**Functions:**

- `jittered_backoff(attempt: int, base_delay: float, max_delay: float, jitter_ratio: float) -> float` — Compute jittered exponential backoff. Returns delay in seconds.
- `retry_with_backoff(fn, max_attempts: int, base_delay: float, retryable_errors: tuple)` — Call fn() up to max_attempts times, with jittered backoff between retries.

### `providers/retry_utils.py`

_Retry utilities — jittered backoff for decorrelated retries._

**Functions:**

- `jittered_backoff(attempt: int, base_delay: float, max_delay: float, jitter_ratio: float) -> float`


---

## (root)

### `queen.py`

_QueenCoordinator — complete Queen coordinator absorption + multi-model consensus._

**Classes:**

- **`ConsensusVerdict`**
- **`VoterResult`**
- **`ConsensusProposal`**
  - `votes(self) -> dict`
- **`QueenDecision`** — reference QueenDecision — typed output from coordination loop.
- **`CoordinationStrategy`**
  - `select_agents(self, agents: list, task: str) -> list`
  - `assign(self, agents: list, subtasks: list) -> dict`
- **`HierarchicalStrategy`**
  - `select_agents(self, agents: list, task: str) -> list`
- **`MeshStrategy`**
  - `select_agents(self, agents: list, task: str) -> list`
- **`AdaptiveStrategy`**
  - `select_agents(self, agents: list, task: str) -> list`
- **`QueenCoordinator`** — Queen coordinator with continuous loops and multi-model consensus.
  - `__init__(self)`
  - `decompose(self, task: str) -> list`
  - `plan(self, task: str, swarm: 'SwarmCoordinator') -> QueenDecision`
  - `set_strategy(self, strategy_name: str) -> None`
  - `start_coordination_loop(self, swarm: 'SwarmCoordinator') -> None`
  - `start_optimization_loop(self, swarm: 'SwarmCoordinator') -> None`
  - `stop_coordination_loop(self) -> None`
  - `build_consensus(self, action: str, context: str, gate_level: str) -> ConsensusProposal`
  - _(+4 more methods)_

**Functions:**

- `chat(model: str, prompt: str) -> str`


---

## (root)

### `repl.py`

_VECTOR — interactive coding REPL (Mode A). VectorCode architecture._

**Classes:**

- **`VectorREPL`** — Mode A: interactive terminal REPL with streaming, skills, compression, persistence.
  - `__init__(self, project_dir: 'Path | None') -> None`
  - `handle_command(self, raw: str) -> str | None`
  - `get_status(self) -> dict`
  - `run(self, skip_startup_banner: bool) -> None`


---

## (root)

### `rl_cli.py`

_RL Training CLI Runner_

**Functions:**

- `load_vector_config() -> dict` — Load configuration from ~/.vectorcode/config.yaml.
- `check_requirements()` — Check that all required environment variables and services are available.
- `check_tinker_atropos()` — Check if tinker-atropos submodule is properly set up.
- `list_environments_sync()` — List available environments (synchronous wrapper).
- `main(task: str, model: str, api_key: str, base_url: str, max_iterations: int, interactive: bool, list_environments: bool, check_server: bool, verbose: bool, save_trajectories: bool)` — RL Training CLI - Dedicated runner for RL training workflows.


---

## (root)

### `router.py`

_GNNRouter — complete reference NeuralDomainMapper absorption._

**Classes:**

- **`DomainNode`** — NeuralDomainMapper.DomainNode — feature vector per model domain.
  - `avg_reward(self) -> float`
- **`DomainEdge`** — NeuralDomainMapper.DomainEdge — cross-domain relationship.
- **`SemanticRouter`** — Layer 3 — static regex fallback. Always works, never learns.
  - `route(self, task: str) -> str`
  - `route_sequence(self, tasks: list) -> list`
  - `count_switches(self, tasks: list) -> int`
- **`NeuralRouter`** — Layer 2 — learned keyword weight matrix via EMA.
  - `__init__(self)`
  - `route(self, task: str) -> str`
  - `learn(self, task: str, model: str, reward: float, latency_ms: float) -> None`
  - `domain_cohesion(self, model: str) -> float`
  - `get_domain_map(self) -> dict[str, dict]`
  - `route_sequence(self, tasks: list) -> list`
  - `count_switches(self, tasks: list) -> int`
- **`GNNRouter`** — Layer 1 — true GNN-style routing with feature vectors and domain graph.
  - `__init__(self)`
  - `route(self, task: str) -> str`
  - `learn(self, task: str, model: str, reward: float, latency_ms: float) -> None`
  - `domain_cohesion(self, model: str) -> float`
  - `get_cross_domain_dependencies(self) -> list[dict]`
  - `optimize_boundaries(self) -> dict[str, str]`
  - `get_domain_map(self) -> dict[str, dict]`


---

## (root)

### `run_agent.py`

_AI Agent Runner with Tool Calling_

**Classes:**

- **`IterationBudget`** — Thread-safe iteration counter for an agent.
  - `__init__(self, max_total: int)`
  - `consume(self) -> bool`
  - `refund(self) -> None`
  - `used(self) -> int`
  - `remaining(self) -> int`
- **`AIAgent`** — AI Agent with tool calling capabilities.
  - `base_url(self) -> str`
  - `base_url(self, value: str) -> None`
  - `__init__(self, base_url: str, api_key: str, provider: str, api_mode: str, acp_command: str, acp_args: list[str] | None, command: str, args: list[str] | None, model: str, max_iterations: int, tool_delay: float, enabled_toolsets: List[str], disabled_toolsets: List[str], save_trajectories: bool, verbose_logging: bool, quiet_mode: bool, ephemeral_system_prompt: str, log_prefix_chars: int, log_prefix: str, providers_allowed: List[str], providers_ignored: List[str], providers_order: List[str], provider_sort: str, provider_require_parameters: bool, provider_data_collection: str, session_id: str, tool_progress_callback: callable, tool_start_callback: callable, tool_complete_callback: callable, thinking_callback: callable, reasoning_callback: callable, clarify_callback: callable, step_callback: callable, stream_delta_callback: callable, interim_assistant_callback: callable, tool_gen_callback: callable, status_callback: callable, max_tokens: int, reasoning_config: Dict[str, Any], service_tier: str, request_overrides: Dict[str, Any], prefill_messages: List[Dict[str, Any]], platform: str, user_id: str, user_name: str, chat_id: str, chat_name: str, chat_type: str, thread_id: str, gateway_session_key: str, skip_context_files: bool, skip_memory: bool, session_db, parent_session_id: str, iteration_budget: 'IterationBudget', fallback_model: Dict[str, Any], credential_pool, checkpoints_enabled: bool, checkpoint_max_snapshots: int, pass_session_id: bool)`
  - `reset_session_state(self)`
  - `switch_model(self, new_model, new_provider, api_key, base_url, api_mode)`
  - `interrupt(self, message: str) -> None`
  - `clear_interrupt(self) -> None`
  - `steer(self, text: str) -> bool`
  - _(+9 more methods)_

**Functions:**

- `main(query: str, model: str, api_key: str, base_url: str, max_turns: int, enabled_toolsets: str, disabled_toolsets: str, list_tools: bool, save_trajectories: bool, save_sample: bool, verbose: bool, log_prefix_chars: int)` — Main function for running the agent directly.


---

## scripts

### `scripts/build_model_catalog.py`

_Build the VectorCode Model Catalog — a centralized JSON manifest of curated models._

**Functions:**

- `build_catalog() -> dict`
- `main() -> int`

### `scripts/build_skills_index.py`

_Build the VectorCode Skills Index — a centralized JSON catalog of all skills._

**Functions:**

- `crawl_source(source, source_name: str, limit: int) -> list` — Crawl a single source and return skill dicts.
- `crawl_skills_sh(source: SkillsShSource) -> list` — Crawl skills.sh using popular queries for broad coverage.
- `batch_resolve_paths(skills: list, auth: GitHubAuth) -> list` — Resolve GitHub paths for skills.sh entries using batch tree lookups.
- `main()`

### `scripts/contributor_audit.py`

_Contributor Audit Script_

**Functions:**

- `is_ignored(handle: str, email: str) -> bool` — Return True if this contributor is a bot/AI/machine account.
- `git(cwd)` — Run a git command and return stdout.
- `gh_pr_list()` — Fetch merged PRs from GitHub using the gh CLI.
- `collect_commit_authors(since_tag, until)` — Collect contributors from git commit authors.
- `collect_co_authors(since_tag, until)` — Collect contributors from Co-authored-by trailers in commit messages.
- `collect_salvaged_contributors(since_tag, until)` — Scan merged PR bodies for salvage/cherry-pick/co-author attribution.
- `check_release_file(release_file, all_contributors)` — Check which contributors are mentioned in the release file.
- `main()`

### `scripts/discord-voice-doctor.py`

_Discord Voice Doctor — diagnostic tool for voice channel support._

**Functions:**

- `mask(value)` — Mask sensitive value: show only first 4 chars.
- `check(label, ok, detail)`
- `warn(label, detail)`
- `section(title)`
- `check_packages()` — Check Python package dependencies. Returns True if all critical deps OK.
- `check_system_tools()` — Check system-level tools (opus, ffmpeg). Returns True if all OK.
- `check_env_vars()` — Check environment variables. Returns (ok, token, groq_key, eleven_key).
- `check_config(groq_key, eleven_key)` — Check vector config.yaml.
- `check_bot_permissions(token)` — Check bot permissions via Discord API. Returns True if all OK.
- `main()`

### `scripts/profile-tui.py`

_Drive the VectorCode TUI under VECTOR_DEV_PERF and summarize the pipeline._

**Functions:**

- `pick_longest_session(db: Path) -> str`
- `drain(fd: int, timeout: float) -> bytes` — Read whatever's available from fd within `timeout`, then return.
- `hold_key(fd: int, seq: bytes, seconds: float, rate_hz: int) -> int` — Write `seq` to fd at ~rate_hz for `seconds`. Returns keystrokes sent.
- `summarize(log: Path, since_ts_ms: int) -> dict[str, Any]` — Parse perf.log, keep only events newer than since_ts_ms, return stats.
- `pct(values: list[float], p: float) -> float`
- `format_report(data: dict[str, Any]) -> str`
- `key_metrics(data: dict[str, Any]) -> dict[str, float]` — Flatten the report into a dict of scalar metrics for A/B diffing.
- `format_diff(before: dict[str, float], after: dict[str, float]) -> str` — Render a side-by-side A/B comparison table.
- `run_once(args: argparse.Namespace) -> dict[str, Any]`
- `main() -> int`
- `loop_mode(args: argparse.Namespace) -> int` — Watch source files, rebuild, rerun, print A/B diff against previous run.
- `wait_for_change(prev: dict[str, float], collect) -> dict[str, float]` — Poll every 1s until a watched file's mtime changes. Debounced 500ms.

### `scripts/release.py`

_VectorCode Release Script_

**Functions:**

- `git(cwd)` — Run a git command and return stdout.
- `git_result(cwd)` — Run a git command and return the full CompletedProcess.
- `get_last_tag()` — Get the most recent CalVer tag.
- `next_available_tag(base_tag: str) -> tuple[str, str]` — Return a tag/calver pair, suffixing same-day releases when needed.
- `get_current_version()` — Read current semver from __init__.py.
- `bump_version(current: str, part: str) -> str` — Bump a semver version string.
- `update_version_files(semver: str, calver_date: str)` — Update version strings in source files.
- `build_release_artifacts(semver: str) -> list[Path]` — Build sdist/wheel artifacts for the current release.
- `resolve_author(name: str, email: str) -> str` — Resolve a git author to a GitHub @mention.
- `categorize_commit(subject: str) -> str` — Categorize a commit by its conventional commit prefix.
- `clean_subject(subject: str) -> str` — Clean up a commit subject for display.
- `parse_coauthors(body: str) -> list` — Extract Co-authored-by trailers from a commit message body.
- `get_commits(since_tag)` — Get commits since a tag (or all commits if None).
- `get_pr_number(subject: str) -> str` — Extract PR number from commit subject if present.
- `generate_changelog(commits, tag_name, semver, repo_url, prev_tag, first_release)` — Generate markdown changelog from categorized commits.
- _(+1 more functions)_

### `scripts/sample_and_compress.py`

_Sample and Compress HuggingFace Datasets_

**Functions:**

- `load_dataset_from_hf(dataset_name: str) -> List[Dict[str, Any]]` — Load a dataset from HuggingFace.
- `sample_from_datasets(datasets: List[str], total_samples: int, min_tokens: int, tokenizer_name: str, seed: int, num_proc: int) -> List[Dict[str, Any]]` — Load all datasets, filter by token count, then randomly sample from combined pool.
- `save_samples_for_compression(samples: List[Dict[str, Any]], output_dir: Path, batch_size: int)` — Save samples to JSONL files for trajectory compression.
- `run_compression(input_dir: Path, output_dir: Path, config_path: str)` — Run trajectory compression on the sampled data.
- `merge_output_to_single_jsonl(input_dir: Path, output_file: Path)` — Merge all JSONL files in a directory into a single JSONL file.
- `main(total_samples: int, output_name: str, datasets: str, config: str, seed: int, batch_size: int, min_tokens: int, num_proc: int, skip_download: bool)` — Sample trajectories from HuggingFace datasets and run compression.


---

## security

### `security/safe_executor.py`

**Classes:**

- **`SafeExecutor`** — Second-layer defence: allowlist check + injection-pattern scan.
  - `is_allowed(self, cmd: list) -> bool`
  - `execute(self, cmd: list, timeout: int) -> dict`

### `security/validator.py`

**Classes:**

- **`ReadFileParams`**
  - `path_not_empty(cls, v: str) -> str`
- **`WriteFileParams`**
  - `path_not_empty(cls, v: str) -> str`
- **`EditFileParams`**
  - `path_not_empty(cls, v: str) -> str`
- **`DeleteFileParams`**
  - `path_not_empty(cls, v: str) -> str`
- **`BashRunParams`**
  - `cmd_not_empty(cls, v: list) -> list`
- **`GrepParams`**
  - `pattern_not_empty(cls, v: str) -> str`
- **`PathValidator`** — Validates that file paths stay within a designated repo root.
  - `__init__(self, repo_root: str) -> None`
  - `validate(self, path: str) -> str`
- **`InputValidator`** — Validates tool call parameters using Pydantic models.
  - `validate_tool_call(self, tool: str, params: dict) -> dict`


---

## (root)

### `session.py`

**Classes:**

- **`TokenUsage`**
  - `total_tokens(self) -> int`
  - `add(self, prompt: int, completion: int, cache_read: int) -> None`
- **`VectorCodeSession`** — Singleton session state shared across all VectorCode agents.
  - `get(cls) -> 'VectorCodeSession'`
  - `reset(self) -> None`
  - `set_mode(self, mode: str) -> None`
  - `record_token_usage(self, prompt: int, completion: int, cache_read: int, cost_usd: float) -> None`
  - `record_file_modified(self, path: str) -> None`
  - `to_dict(self) -> dict`
  - `save(self, sessions_dir: Path) -> Path`


---

## (root)

### `session_db.py`

_VectorCode SQLite session database with FTS5 full-text search._

**Classes:**

- **`SessionDB`** — SQLite-backed session store with FTS5 full-text search.
  - `__init__(self, db_path: 'Path | None') -> None`
  - `close(self) -> None`
  - `create_session(self, session_id: str, model: str, project: str, mode: str) -> None`
  - `end_session(self, session_id: str, end_reason: str) -> None`
  - `get_session(self, session_id: str) -> Optional[Dict]`
  - `list_sessions(self, limit: int) -> List[Dict]`
  - `delete_session(self, session_id: str) -> bool`
  - `add_message(self, session_id: str, role: str, content: str, token_count: int, finish_reason: str) -> str`
  - _(+7 more methods)_

**Functions:**

- `get_session_db() -> SessionDB` — Return the module-level singleton SessionDB instance.


---

## (root)

### `swarm.py`

_SwarmCoordinator — complete reference swarm topology absorption._

**Classes:**

- **`Topology`**
- **`AgentState`** — Per-agent runtime state tracked by SwarmCoordinator.
  - `__init__(self, agent)`
  - `start_task(self, task: str) -> None`
  - `complete_task(self) -> None`
  - `fail_task(self) -> None`
  - `to_dict(self) -> dict`
- **`SwarmCoordinator`** — Manages pools of specialized agents across 8 topology strategies.
  - `__init__(self, topology: Topology, max_agents: int, quorum_size: int, gossip_fanout: int, byzantine_f: int) -> None`
  - `spawn(self, agent_type: str)`
  - `list_agents(self) -> List`
  - `get_state(self, agent_id: str) -> Optional[AgentState]`
  - `assign_task(self, agent_id: str, task: str) -> bool`
  - `complete_task(self, agent_id: str) -> bool`
  - `shutdown(self) -> None`
  - `route_to_domain(self, task: str) -> str`
  - _(+7 more methods)_


---

## tools

### `tools/ansi_strip.py`

_Strip ANSI escape sequences from subprocess output._

**Functions:**

- `strip_ansi(text: str) -> str` — Remove ANSI escape sequences from text.

### `tools/approval.py`

_Dangerous command approval -- detection, prompting, and per-session state._

**Functions:**

- `set_current_session_key(session_key: str) -> contextvars.Token[str]` — Bind the active approval session key to the current context.
- `reset_current_session_key(token: contextvars.Token[str]) -> None` — Restore the prior approval session key context.
- `get_current_session_key(default: str) -> str` — Return the active session key, preferring context-local state.
- `detect_hardline_command(command: str) -> tuple` — Check if a command matches the unconditional hardline blocklist.
- `detect_dangerous_command(command: str) -> tuple` — Check if a command matches any dangerous patterns.
- `register_gateway_notify(session_key: str, cb) -> None` — Register a per-session callback for sending approval requests to the user.
- `unregister_gateway_notify(session_key: str) -> None` — Unregister the per-session gateway approval callback.
- `resolve_gateway_approval(session_key: str, choice: str, resolve_all: bool) -> int` — Called by the gateway's /approve or /deny handler to unblock
- `has_blocking_approval(session_key: str) -> bool` — Check if a session has one or more blocking gateway approvals waiting.
- `submit_pending(session_key: str, approval: dict)` — Store a pending approval request for a session.
- `approve_session(session_key: str, pattern_key: str)` — Approve a pattern for this session only.
- `enable_session_yolo(session_key: str) -> None` — Enable YOLO bypass for a single session key.
- `disable_session_yolo(session_key: str) -> None` — Disable YOLO bypass for a single session key.
- `clear_session(session_key: str) -> None` — Remove all approval and yolo state for a given session.
- `is_session_yolo_enabled(session_key: str) -> bool` — Return True when YOLO bypass is enabled for a specific session.
- _(+9 more functions)_

### `tools/bash_tools.py`

**Classes:**

- **`BashTools`** — Safe subprocess wrapper.
  - `is_allowed(self, cmd: list) -> bool`
  - `run(self, cmd: list, timeout: int, cwd: str) -> subprocess.CompletedProcess`

### `tools/binary_extensions.py`

_Binary file extensions to skip for text-based operations._

**Functions:**

- `has_binary_extension(path: str) -> bool` — Check if a file path has a binary extension. Pure string check, no I/O.

### `tools/browser_camofox.py`

_Camofox browser backend — local anti-detection browser via REST API._

**Functions:**

- `get_camofox_url() -> str` — Return the configured Camofox server URL, or empty string.
- `is_camofox_mode() -> bool` — True when Camofox backend is configured and no CDP override is active.
- `check_camofox_available() -> bool` — Verify the Camofox server is reachable.
- `get_vnc_url() -> Optional[str]` — Return the VNC URL if the Camofox server exposes one, or None.
- `camofox_soft_cleanup(task_id: Optional[str]) -> bool` — Release the in-memory session without destroying the server-side context.
- `camofox_navigate(url: str, task_id: Optional[str]) -> str` — Navigate to a URL via Camofox.
- `camofox_snapshot(full: bool, task_id: Optional[str], user_task: Optional[str]) -> str` — Get accessibility tree snapshot from Camofox.
- `camofox_click(ref: str, task_id: Optional[str]) -> str` — Click an element by ref via Camofox.
- `camofox_type(ref: str, text: str, task_id: Optional[str]) -> str` — Type text into an element by ref via Camofox.
- `camofox_scroll(direction: str, task_id: Optional[str]) -> str` — Scroll the page via Camofox.
- `camofox_back(task_id: Optional[str]) -> str` — Navigate back via Camofox.
- `camofox_press(key: str, task_id: Optional[str]) -> str` — Press a keyboard key via Camofox.
- `camofox_close(task_id: Optional[str]) -> str` — Close the browser session via Camofox.
- `camofox_get_images(task_id: Optional[str]) -> str` — Get images on the current page via Camofox.
- `camofox_vision(question: str, annotate: bool, task_id: Optional[str]) -> str` — Take a screenshot and analyze it with vision AI via Camofox.
- _(+1 more functions)_

### `tools/browser_camofox_state.py`

_VectorCode-managed Camofox state helpers._

**Functions:**

- `get_camofox_state_dir() -> Path` — Return the profile-scoped root directory for Camofox persistence.
- `get_camofox_identity(task_id: Optional[str]) -> Dict[str, str]` — Return the stable VectorCode-managed Camofox identity for this profile.

### `tools/browser_cdp_tool.py`

_Raw Chrome DevTools Protocol (CDP) passthrough tool._

**Functions:**

- `browser_cdp(method: str, params: Optional[Dict[str, Any]], target_id: Optional[str], frame_id: Optional[str], timeout: float, task_id: Optional[str]) -> str` — Send a raw CDP command.  See ``CDP_DOCS_URL`` for method documentation.

### `tools/browser_dialog_tool.py`

_Agent-facing tool: respond to a native JS dialog captured by the CDP supervisor._

**Functions:**

- `browser_dialog(action: str, prompt_text: Optional[str], dialog_id: Optional[str], task_id: Optional[str]) -> str` — Respond to a pending dialog on the active task's CDP supervisor.

### `tools/browser_supervisor.py`

_Persistent CDP supervisor for browser dialog + frame detection._

**Classes:**

- **`PendingDialog`** — A JS dialog currently open on some frame's session.
  - `to_dict(self) -> Dict[str, Any]`
- **`DialogRecord`** — A historical record of a dialog that was opened and then handled.
  - `to_dict(self) -> Dict[str, Any]`
- **`FrameInfo`** — One frame in the page's frame tree.
  - `to_dict(self) -> Dict[str, Any]`
- **`ConsoleEvent`** — Ring buffer entry for console + exception traffic.
- **`SupervisorSnapshot`** — Read-only snapshot of supervisor state.
  - `to_dict(self) -> Dict[str, Any]`
- **`CDPSupervisor`** — One supervisor per (task_id, cdp_url) pair.
  - `__init__(self, task_id: str, cdp_url: str, dialog_policy: str, dialog_timeout_s: float) -> None`
  - `start(self, timeout: float) -> None`
  - `stop(self, timeout: float) -> None`
  - `snapshot(self) -> SupervisorSnapshot`
  - `respond_to_dialog(self, action: str, prompt_text: Optional[str], dialog_id: Optional[str], timeout: float) -> Dict[str, Any]`

### `tools/browser_tool.py`

_Browser Tool Module_

**Functions:**

- `browser_navigate(url: str, task_id: Optional[str]) -> str` — Navigate to a URL in the browser.
- `browser_snapshot(full: bool, task_id: Optional[str], user_task: Optional[str]) -> str` — Get a text-based snapshot of the current page's accessibility tree.
- `browser_click(ref: str, task_id: Optional[str]) -> str` — Click on an element.
- `browser_type(ref: str, text: str, task_id: Optional[str]) -> str` — Type text into an input field.
- `browser_scroll(direction: str, task_id: Optional[str]) -> str` — Scroll the page.
- `browser_back(task_id: Optional[str]) -> str` — Navigate back in browser history.
- `browser_press(key: str, task_id: Optional[str]) -> str` — Press a keyboard key.
- `browser_console(clear: bool, expression: Optional[str], task_id: Optional[str]) -> str` — Get browser console messages and JavaScript errors, or evaluate JS in the page.
- `browser_get_images(task_id: Optional[str]) -> str` — Get all images on the current page.
- `browser_vision(question: str, annotate: bool, task_id: Optional[str]) -> str` — Take a screenshot of the current page and analyze it with vision AI.
- `cleanup_browser(task_id: Optional[str]) -> None` — Clean up browser session(s) for a task.
- `cleanup_all_browsers() -> None` — Clean up all active browser sessions.
- `check_browser_requirements() -> bool` — Check if browser tool requirements are met.

### `tools/browser_tools.py`

_BrowserTools — Playwright-based browser automation for VECTOR's coding district._

**Classes:**

- **`BrowserTools`** — Playwright browser automation with VECTOR permission gating.
  - `__init__(self)`
  - `navigate(self, url: str) -> str`
  - `screenshot(self, path: str | None) -> bytes`
  - `click(self, selector: str) -> bool`
  - `extract_text(self, selector: str) -> str`
  - `submit_form(self, selector: str, data: dict) -> bool`
  - `close(self) -> None`

### `tools/budget_config.py`

_Configurable budget constants for tool result persistence._

**Classes:**

- **`BudgetConfig`** — Immutable budget constants for the 3-layer tool result persistence system.
  - `resolve_threshold(self, tool_name: str) -> int | float`

### `tools/checkpoint.py`

_VectorCode Checkpoint Tool — ported from VectorCode checkpoint_manager.py._

**Classes:**

- **`CheckpointManager`** — Manages filesystem snapshots via a shadow git repo.
  - `__init__(self, work_dir: Path, max_snapshots: int)`
  - `create_checkpoint(self, label: str) -> Dict[str, Any]`
  - `list_checkpoints(self) -> List[Dict[str, Any]]`
  - `restore_checkpoint(self, commit_hash: str, force: bool) -> Dict[str, Any]`
  - `diff_from_checkpoint(self, commit_hash: str) -> str`

### `tools/checkpoint_manager.py`

_Checkpoint Manager — Transparent filesystem snapshots via shadow git repos._

**Classes:**

- **`CheckpointManager`** — Manages automatic filesystem checkpoints.
  - `__init__(self, enabled: bool, max_snapshots: int)`
  - `new_turn(self) -> None`
  - `ensure_checkpoint(self, working_dir: str, reason: str) -> bool`
  - `list_checkpoints(self, working_dir: str) -> List[Dict]`
  - `diff(self, working_dir: str, commit_hash: str) -> Dict`
  - `restore(self, working_dir: str, commit_hash: str, file_path: str) -> Dict`
  - `get_working_dir_for_path(self, file_path: str) -> str`

**Functions:**

- `format_checkpoint_list(checkpoints: List[Dict], directory: str) -> str` — Format checkpoint list for display to user.
- `prune_checkpoints(retention_days: int, delete_orphans: bool, checkpoint_base: Optional[Path]) -> Dict[str, int]` — Delete stale/orphan shadow repos under ``checkpoint_base``.
- `maybe_auto_prune_checkpoints(retention_days: int, min_interval_hours: int, delete_orphans: bool, checkpoint_base: Optional[Path]) -> Dict[str, object]` — Idempotent wrapper around ``prune_checkpoints`` for startup hooks.

### `tools/clarify_tool.py`

_Clarify Tool Module - Interactive Clarifying Questions_

**Functions:**

- `clarify_tool(question: str, choices: Optional[List[str]], callback: Optional[Callable]) -> str` — Ask the user a question, optionally with multiple-choice options.
- `check_clarify_requirements() -> bool` — Clarify tool has no external requirements -- always available.

### `tools/code_execution.py`

_Code execution sandbox — runs Python scripts in isolated subprocess._

**Functions:**

- `execute_code(code: str, timeout: int, workdir: Optional[Path], env_overrides: Optional[dict]) -> dict` — Execute Python code in a subprocess sandbox.

### `tools/code_execution_tool.py`

_Code Execution Tool -- Programmatic Tool Calling (PTC)_

**Functions:**

- `check_sandbox_requirements() -> bool` — Code execution sandbox requires a POSIX OS for Unix domain sockets.
- `generate_vector_tools_module(enabled_tools: List[str], transport: str) -> str` — Build the source code for the vector_tools.py stub module.
- `execute_code(code: str, task_id: Optional[str], enabled_tools: Optional[List[str]]) -> str` — Run a Python script in a sandboxed child process with RPC access
- `build_execute_code_schema(enabled_sandbox_tools: set, mode: str) -> dict` — Build the execute_code schema with description listing only enabled tools.

### `tools/code_graph.py`

_CodeGraph — AST-based code intelligence for VECTOR's coding district._

**Classes:**

- **`CodeGraph`** — Incremental AST index with blast-radius analysis.
  - `__init__(self, repo_root: str, db_path: str)`
  - `index_file(self, rel_path: str) -> int`
  - `index_repo(self, extensions: list[str] | None) -> int`
  - `list_symbols(self, rel_path: str) -> list[str]`
  - `list_all_symbols(self) -> list[str]`
  - `blast_radius(self, symbol_name: str) -> list[str]`
  - `dependents(self, rel_path: str) -> list[str]`
  - `close(self) -> None`

### `tools/credential_files.py`

_File passthrough registry for remote terminal backends._

**Functions:**

- `register_credential_file(relative_path: str, container_base: str) -> bool` — Register a credential file for mounting into remote sandboxes.
- `register_credential_files(entries: list, container_base: str) -> List[str]` — Register multiple credential files from skill frontmatter entries.
- `get_credential_file_mounts() -> List[Dict[str, str]]` — Return all credential files that should be mounted into remote sandboxes.
- `get_skills_directory_mount(container_base: str) -> list[Dict[str, str]]` — Return mount info for all skill directories (local + external).
- `iter_skills_files(container_base: str) -> List[Dict[str, str]]` — Yield individual (host_path, container_path) entries for skills files.
- `get_cache_directory_mounts(container_base: str) -> List[Dict[str, str]]` — Return mount entries for each cache directory that exists on disk.
- `iter_cache_files(container_base: str) -> List[Dict[str, str]]` — Return individual (host_path, container_path) entries for cache files.
- `clear_credential_files() -> None` — Reset the skill-scoped registry (e.g. on session reset).

### `tools/cronjob_tools.py`

_Cron job management tools for VectorCode._

**Functions:**

- `cronjob(action: str, job_id: Optional[str], prompt: Optional[str], schedule: Optional[str], name: Optional[str], repeat: Optional[int], deliver: Optional[str], include_disabled: bool, skill: Optional[str], skills: Optional[List[str]], model: Optional[str], provider: Optional[str], base_url: Optional[str], reason: Optional[str], script: Optional[str], context_from: Optional[Union[str, List[str]]], enabled_toolsets: Optional[List[str]], workdir: Optional[str], task_id: str) -> str` — Unified cron job management tool.
- `check_cronjob_requirements() -> bool` — Check if cronjob tools can be used.

### `tools/debug_helpers.py`

_Shared debug session infrastructure for VectorCode tools._

**Classes:**

- **`DebugSession`** — Per-tool debug session that records tool calls to a JSON log file.
  - `__init__(self, tool_name: str, env_var: str) -> None`
  - `active(self) -> bool`
  - `log_call(self, call_name: str, call_data: Dict[str, Any]) -> None`
  - `save(self) -> None`
  - `get_session_info(self) -> Dict[str, Any]`

### `tools/delegate.py`

_VectorCode delegate_task tool — subagent architecture._

**Classes:**

- **`DelegateTask`** — Parameters for a single delegation request.
- **`DelegateResult`** — Outcome of a delegation request.
  - `to_dict(self) -> Dict[str, Any]`

**Functions:**

- `delegate_task(task: str, context: str, max_iterations: int, timeout: int) -> DelegateResult` — Delegate a task to an independent subagent and return its result.
- `handle_delegate_task(args: Dict[str, Any]) -> str` — Tool handler — wraps delegate_task() for the VectorCode tool registry.

### `tools/delegate_tool.py`

_Delegate Tool -- Subagent Architecture_

**Classes:**

- **`DelegateEvent`** — Formal event types emitted during delegation progress.

**Functions:**

- `set_spawn_paused(paused: bool) -> bool` — Globally block/unblock new delegate_task spawns.
- `is_spawn_paused() -> bool`
- `interrupt_subagent(subagent_id: str) -> bool` — Request that a single running subagent stop at its next iteration boundary.
- `list_active_subagents() -> List[Dict[str, Any]]` — Snapshot of the currently running subagent tree.
- `check_delegate_requirements() -> bool` — Delegation has no external requirements -- always available.
- `delegate_task(goal: Optional[str], context: Optional[str], toolsets: Optional[List[str]], tasks: Optional[List[Dict[str, Any]]], max_iterations: Optional[int], acp_command: Optional[str], acp_args: Optional[List[str]], role: Optional[str], parent_agent) -> str` — Spawn one or more child agents to handle delegated tasks.

### `tools/direct_executor.py`

_Direct Task Executor for Swarm — executes tasks without external CLI._

**Classes:**

- **`TaskResult`**
  - `__init__(self, output: str, artifacts: Optional[dict], execution_time: float, agent_type: str, quality: float, completeness: float, validated: bool)`
- **`DirectTaskExecutor`**
  - `__init__(self, timeout: int)`
  - `execute(self, task_desc: str, tools: Optional[list]) -> TaskResult`

### `tools/discord_tool.py`

_Discord server introspection and management tool._

**Classes:**

- **`DiscordAPIError`** — Raised when a Discord API call fails.
  - `__init__(self, status: int, body: str)`

**Functions:**

- `get_dynamic_schema_core() -> Optional[Dict[str, Any]]`
- `get_dynamic_schema_admin() -> Optional[Dict[str, Any]]`
- `get_dynamic_schema() -> Optional[Dict[str, Any]]` — Backward-compat wrapper — returns core schema.
- `check_discord_tool_requirements() -> bool` — Tool is available only when a Discord bot token is configured.
- `discord_core(action: str) -> str` — Execute a core Discord action (fetch_messages, search_members, create_thread).
- `discord_admin_handler(action: str) -> str` — Execute a Discord admin action (server management).

### `tools/env_passthrough.py`

_Environment variable passthrough registry._

**Functions:**

- `register_env_passthrough(var_names: Iterable[str]) -> None` — Register environment variable names as allowed in sandboxed environments.
- `is_env_passthrough(var_name: str) -> bool` — Check whether *var_name* is allowed to pass through to sandboxes.
- `get_all_passthrough() -> frozenset[str]` — Return the union of skill-registered and config-based passthrough vars.
- `clear_env_passthrough() -> None` — Reset the skill-scoped allowlist (e.g. on session reset).

### `tools/environments/base.py`

_Base class for all VectorCode execution environment backends._

**Classes:**

- **`ProcessHandle`** — Duck type that every backend's _run_bash() must return.
  - `poll(self) -> int | None`
  - `kill(self) -> None`
  - `wait(self, timeout: float | None) -> int`
  - `stdout(self) -> IO[str] | None`
  - `returncode(self) -> int | None`
- **`BaseEnvironment`** — Common interface and unified execution flow for all VectorCode backends.
  - `get_temp_dir(self) -> str`
  - `__init__(self, cwd: str, timeout: int, env: dict)`
  - `cleanup(self)`
  - `init_session(self)`
  - `execute(self, command: str, cwd: str, timeout: int | None, stdin_data: str | None) -> dict`
  - `stop(self)`

**Functions:**

- `set_activity_callback(cb: Callable[[str], None] | None) -> None` — Register a callback that _wait_for_process fires periodically.
- `touch_activity_if_due(state: dict, label: str) -> None` — Fire the activity callback at most once every ``state['interval']`` seconds.
- `get_sandbox_dir() -> Path` — Return the host-side root for all sandbox storage (Docker workspaces,

### `tools/environments/daytona.py`

_Daytona cloud execution environment._

**Classes:**

- **`DaytonaEnvironment`** — Daytona cloud sandbox execution backend.
  - `__init__(self, image: str, cwd: str, timeout: int, cpu: int, memory: int, disk: int, persistent_filesystem: bool, task_id: str)`
  - `cleanup(self)`

### `tools/environments/docker.py`

_Docker execution environment for sandboxed command execution._

**Classes:**

- **`DockerEnvironment`** — Hardened Docker container execution with resource limits and persistence.
  - `__init__(self, image: str, cwd: str, timeout: int, cpu: float, memory: int, disk: int, persistent_filesystem: bool, task_id: str, volumes: list, forward_env: list[str] | None, env: dict | None, network: bool, host_cwd: str, auto_mount_cwd: bool)`
  - `cleanup(self)`

**Functions:**

- `find_docker() -> Optional[str]` — Locate the docker (or podman) CLI binary.

### `tools/environments/file_sync.py`

_Shared file sync manager for remote execution backends._

**Classes:**

- **`FileSyncManager`** — Tracks local file changes and syncs to a remote environment.
  - `__init__(self, get_files_fn: GetFilesFn, upload_fn: UploadFn, delete_fn: DeleteFn, sync_interval: float, bulk_upload_fn: BulkUploadFn | None, bulk_download_fn: BulkDownloadFn | None)`
  - `sync(self, force: bool) -> None`
  - `sync_back(self, vector_home: Path | None) -> None`

**Functions:**

- `iter_sync_files(container_base: str) -> list[tuple[str, str]]` — Enumerate all files that should be synced to a remote environment.
- `quoted_rm_command(remote_paths: list[str]) -> str` — Build a shell ``rm -f`` command for a batch of remote paths.
- `quoted_mkdir_command(dirs: list[str]) -> str` — Build a shell ``mkdir -p`` command for a batch of directories.
- `unique_parent_dirs(files: list[tuple[str, str]]) -> list[str]` — Extract sorted unique parent directories from (host, remote) pairs.

### `tools/environments/local.py`

_Local execution environment — spawn-per-call with session snapshot._

**Classes:**

- **`LocalEnvironment`** — Run commands directly on the host machine.
  - `__init__(self, cwd: str, timeout: int, env: dict)`
  - `get_temp_dir(self) -> str`
  - `cleanup(self)`

### `tools/environments/managed_modal.py`

_Managed Modal environment backed by tool-gateway._

**Classes:**

- **`ManagedModalEnvironment`** — Gateway-owned Modal sandbox with VectorCode-compatible execute/cleanup.
  - `__init__(self, image: str, cwd: str, timeout: int, modal_sandbox_kwargs: Optional[Dict[str, Any]], persistent_filesystem: bool, task_id: str)`
  - `cleanup(self)`

### `tools/environments/modal.py`

_Modal cloud execution environment using the native Modal SDK directly._

**Classes:**

- **`ModalEnvironment`** — Modal cloud execution via native Modal sandboxes.
  - `__init__(self, image: str, cwd: str, timeout: int, modal_sandbox_kwargs: Optional[dict[str, Any]], persistent_filesystem: bool, task_id: str)`
  - `cleanup(self)`

### `tools/environments/modal_utils.py`

_Shared VectorCode-side execution flow for Modal transports._

**Classes:**

- **`PreparedModalExec`** — Normalized command data passed to a transport-specific exec runner.
- **`ModalExecStart`** — Transport response after starting an exec.
- **`BaseModalExecutionEnvironment`** — Execution flow for the *managed* Modal transport (gateway-owned sandbox).
  - `execute(self, command: str, cwd: str, timeout: int | None, stdin_data: str | None) -> dict`

**Functions:**

- `wrap_modal_stdin_heredoc(command: str, stdin_data: str) -> str` — Append stdin as a shell heredoc for transports without stdin piping.
- `wrap_modal_sudo_pipe(command: str, sudo_stdin: str) -> str` — Feed sudo via a shell pipe for transports without direct stdin piping.

### `tools/environments/singularity.py`

_Singularity/Apptainer persistent container environment._

**Classes:**

- **`SingularityEnvironment`** — Hardened Singularity/Apptainer container with resource limits and persistence.
  - `__init__(self, image: str, cwd: str, timeout: int, cpu: float, memory: int, disk: int, persistent_filesystem: bool, task_id: str)`
  - `cleanup(self)`

### `tools/environments/ssh.py`

_SSH remote execution environment with ControlMaster connection persistence._

**Classes:**

- **`SSHEnvironment`** — Run commands on a remote machine over SSH.
  - `__init__(self, host: str, user: str, cwd: str, timeout: int, port: int, key_path: str)`
  - `cleanup(self)`

### `tools/feishu_doc_tool.py`

_Feishu Document Tool -- read document content via Feishu/Lark API._

**Functions:**

- `set_client(client)` — Store a lark client for the current thread (called by feishu_comment).
- `get_client()` — Return the lark client for the current thread, or None.

### `tools/feishu_drive_tool.py`

_Feishu Drive Tools -- document comment operations via Feishu/Lark API._

**Functions:**

- `set_client(client)` — Store a lark client for the current thread (called by feishu_comment).
- `get_client()` — Return the lark client for the current thread, or None.

### `tools/file_operations.py`

_File Operations Module_

**Classes:**

- **`ReadResult`** — Result from reading a file.
  - `to_dict(self) -> dict`
- **`WriteResult`** — Result from writing a file.
  - `to_dict(self) -> dict`
- **`PatchResult`** — Result from patching a file.
  - `to_dict(self) -> dict`
- **`SearchMatch`** — A single search match.
- **`SearchResult`** — Result from searching.
  - `to_dict(self) -> dict`
- **`LintResult`** — Result from linting a file.
  - `to_dict(self) -> dict`
- **`ExecuteResult`** — Result from executing a shell command.
- **`FileOperations`** — Abstract interface for file operations across terminal backends.
  - `read_file(self, path: str, offset: int, limit: int) -> ReadResult`
  - `read_file_raw(self, path: str) -> ReadResult`
  - `write_file(self, path: str, content: str) -> WriteResult`
  - `patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool) -> PatchResult`
  - `patch_v4a(self, patch_content: str) -> PatchResult`
  - `delete_file(self, path: str) -> WriteResult`
  - `move_file(self, src: str, dst: str) -> WriteResult`
  - `search(self, pattern: str, path: str, target: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult`
- **`ShellFileOperations`** — File operations implemented via shell commands.
  - `__init__(self, terminal_env, cwd: str)`
  - `read_file(self, path: str, offset: int, limit: int) -> ReadResult`
  - `read_file_raw(self, path: str) -> ReadResult`
  - `delete_file(self, path: str) -> WriteResult`
  - `move_file(self, src: str, dst: str) -> WriteResult`
  - `write_file(self, path: str, content: str) -> WriteResult`
  - `patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool) -> PatchResult`
  - `patch_v4a(self, patch_content: str) -> PatchResult`
  - _(+1 more methods)_

**Functions:**

- `normalize_read_pagination(offset: Any, limit: Any) -> tuple[int, int]` — Return safe read_file pagination bounds.
- `normalize_search_pagination(offset: Any, limit: Any) -> tuple[int, int]` — Return safe search pagination bounds for shell head/tail pipelines.

### `tools/file_safety.py`

_File write/read safety rules._

**Functions:**

- `build_write_denied_paths(home: str) -> set[str]`
- `build_write_denied_prefixes(home: str) -> list[str]`
- `is_write_denied(path: str) -> bool` — Return True if path is blocked by the write denylist.
- `is_safe_to_read(path: str) -> bool` — Return True if path is safe to read (not an internal cache file).

### `tools/file_state.py`

_Cross-agent file state coordination._

**Classes:**

- **`FileStateRegistry`** — Process-wide coordinator for cross-agent file edits.
  - `__init__(self) -> None`
  - `lock_path(self, resolved: str)`
  - `record_read(self, task_id: str, resolved: str, partial: bool, mtime: Optional[float]) -> None`
  - `note_write(self, task_id: str, resolved: str, mtime: Optional[float]) -> None`
  - `check_stale(self, task_id: str, resolved: str) -> Optional[str]`
  - `writes_since(self, exclude_task_id: str, since_ts: float, paths: Iterable[str]) -> Dict[str, List[str]]`
  - `known_reads(self, task_id: str) -> List[str]`
  - `clear(self) -> None`

**Functions:**

- `get_registry() -> FileStateRegistry`
- `record_read(task_id: str, resolved_or_path: str | Path, partial: bool) -> None`
- `note_write(task_id: str, resolved_or_path: str | Path) -> None`
- `check_stale(task_id: str, resolved_or_path: str | Path) -> Optional[str]`
- `lock_path(resolved_or_path: str | Path)`
- `writes_since(exclude_task_id: str, since_ts: float, paths: Iterable[str | Path]) -> Dict[str, List[str]]`
- `known_reads(task_id: str) -> List[str]`

### `tools/file_tools.py`

_File Tools Module - LLM agent file manipulation tools._

**Functions:**

- `clear_file_ops_cache(task_id: str)` — Clear the file operations cache.
- `read_file_tool(path: str, offset: int, limit: int, task_id: str) -> str` — Read a file with pagination and line numbers.
- `reset_file_dedup(task_id: str)` — Clear the deduplication cache for file reads.
- `notify_other_tool_call(task_id: str)` — Reset consecutive read/search counter for a task.
- `write_file_tool(path: str, content: str, task_id: str) -> str` — Write content to a file.
- `patch_tool(mode: str, path: str, old_string: str, new_string: str, replace_all: bool, patch: str, task_id: str) -> str` — Patch a file using replace mode or V4A patch format.
- `search_tool(pattern: str, target: str, path: str, file_glob: str, limit: int, offset: int, output_mode: str, context: int, task_id: str) -> str` — Search for content or files.

### `tools/fuzzy_match.py`

_Fuzzy Matching Module for File Operations_

**Functions:**

- `fuzzy_find_and_replace(content: str, old_string: str, new_string: str, replace_all: bool) -> Tuple[str, int, Optional[str], Optional[str]]` — Find and replace text using a chain of increasingly fuzzy matching strategies.
- `find_closest_lines(old_string: str, content: str, context_lines: int, max_results: int) -> str` — Find lines in content most similar to old_string for "did you mean?" feedback.
- `format_no_match_hint(error: Optional[str], match_count: int, old_string: str, content: str) -> str` — Return a '\n\nDid you mean...' snippet for plain no-match errors.

### `tools/git_tools.py`

_Git tools for VectorCode — git_status, git_diff, git_log, git_commit,_

**Classes:**

- **`GitTools`** — Git operations scoped to a repository root.
  - `__init__(self, repo_root: str | Path) -> None`
  - `git_status(self) -> str`
  - `git_diff(self, staged: bool, path: str) -> str`
  - `git_log(self, n: int, oneline: bool) -> str`
  - `git_blame(self, path: str, start: int, end: int) -> str`
  - `git_commit(self, message: str, add_all: bool) -> str`
  - `git_create_branch(self, name: str, checkout: bool) -> str`
  - `git_push(self, remote: str, branch: str) -> str`
  - _(+3 more methods)_

### `tools/homeassistant_tool.py`

_Home Assistant tool for controlling smart home devices via REST API._

### `tools/image_gen.py`

_Image generation and vision analysis tools._

**Functions:**

- `generate_image(prompt: str, model: str, backend: str, api_key: Optional[str], size: str, num_images: int, output_dir: Optional[str]) -> dict` — Generate one or more images from a text prompt.
- `describe_image(image_path_or_url: str, question: str, model_id: str) -> dict` — Analyse an image with a vision model.
- `get_tool_schemas() -> list[dict]` — Return OpenAI-format tool schemas for generate_image and describe_image.

### `tools/image_generation_tool.py`

_Image Generation Tools Module_

**Functions:**

- `image_generate_tool(prompt: str, aspect_ratio: str, num_inference_steps: Optional[int], guidance_scale: Optional[float], num_images: Optional[int], output_format: Optional[str], seed: Optional[int]) -> str` — Generate an image from a text prompt using the configured FAL model.
- `check_fal_api_key() -> bool` — True if the FAL.ai API key (direct or managed gateway) is available.
- `check_image_generation_requirements() -> bool` — True if any image gen backend is available.

### `tools/interrupt.py`

_Per-thread interrupt signaling for all tools._

**Functions:**

- `set_interrupt(active: bool, thread_id: int | None) -> None` — Set or clear interrupt for a specific thread.
- `is_interrupted() -> bool` — Check if an interrupt has been requested for the current thread.

### `tools/managed_tool_gateway.py`

_Generic managed-tool gateway helpers for Nous-hosted vendor passthroughs._

**Classes:**

- **`ManagedToolGatewayConfig`**

**Functions:**

- `auth_json_path()` — Return the VectorCode auth store path, respecting VECTOR_HOME overrides.
- `read_nous_access_token() -> Optional[str]` — Read a Nous Subscriber OAuth access token from auth store or env override.
- `get_tool_gateway_scheme() -> str` — Return configured shared gateway URL scheme.
- `build_vendor_gateway_url(vendor: str) -> str` — Return the gateway origin for a specific vendor.
- `resolve_managed_tool_gateway(vendor: str, gateway_builder: Optional[Callable[[str], str]], token_reader: Optional[Callable[[], Optional[str]]]) -> Optional[ManagedToolGatewayConfig]` — Resolve shared managed-tool gateway config for a vendor.
- `is_managed_tool_gateway_ready(vendor: str, gateway_builder: Optional[Callable[[str], str]], token_reader: Optional[Callable[[], Optional[str]]]) -> bool` — Return True when gateway URL and Nous access token are available.

### `tools/mcp_oauth.py`

_MCP OAuth 2.1 Client Support_

**Classes:**

- **`OAuthNonInteractiveError`** — Raised when OAuth requires browser interaction in a non-interactive env.
- **`VectorCodeTokenStorage`** — Persist OAuth tokens and client registration to JSON files.
  - `__init__(self, server_name: str)`
  - `get_tokens(self) -> 'OAuthToken | None'`
  - `set_tokens(self, tokens: 'OAuthToken') -> None`
  - `get_client_info(self) -> 'OAuthClientInformationFull | None'`
  - `set_client_info(self, client_info: 'OAuthClientInformationFull') -> None`
  - `remove(self) -> None`
  - `has_cached_tokens(self) -> bool`

**Functions:**

- `remove_oauth_tokens(server_name: str) -> None` — Delete stored OAuth tokens and client info for a server.
- `build_oauth_auth(server_name: str, server_url: str, oauth_config: dict | None) -> 'OAuthClientProvider | None'` — Build an ``httpx.Auth``-compatible OAuth handler for an MCP server.

### `tools/mcp_oauth_manager.py`

_Central manager for per-server MCP OAuth state._

**Classes:**

- **`MCPOAuthManager`** — Single source of truth for per-server MCP OAuth state.
  - `__init__(self) -> None`
  - `get_or_build_provider(self, server_name: str, server_url: str, oauth_config: Optional[dict]) -> Optional[Any]`
  - `remove(self, server_name: str) -> None`
  - `invalidate_if_disk_changed(self, server_name: str) -> bool`
  - `handle_401(self, server_name: str, failed_access_token: Optional[str]) -> bool`

**Functions:**

- `get_manager() -> MCPOAuthManager` — Return the process-wide :class:`MCPOAuthManager` singleton.
- `reset_manager_for_tests() -> None` — Test-only helper: drop the singleton so fixtures start clean.

### `tools/mcp_tool.py`

_MCP (Model Context Protocol) Client Support_

**Classes:**

- **`SamplingHandler`** — Handles sampling/createMessage requests for a single MCP server.
  - `__init__(self, server_name: str, config: dict)`
  - `session_kwargs(self) -> dict`
- **`MCPServerTask`** — Manages a single MCP server connection in a dedicated asyncio Task.
  - `__init__(self, name: str)`
  - `run(self, config: dict)`
  - `start(self, config: dict)`
  - `shutdown(self)`

**Functions:**

- `sanitize_mcp_name_component(value: str) -> str` — Return an MCP name component safe for tool and prefix generation.
- `register_mcp_servers(servers: Dict[str, dict]) -> List[str]` — Connect to explicit MCP servers and register their tools.
- `discover_mcp_tools() -> List[str]` — Entry point: load config, connect to MCP servers, register tools.
- `get_mcp_status() -> List[dict]` — Return status of all configured MCP servers for banner display.
- `probe_mcp_server_tools() -> Dict[str, List[tuple]]` — Temporarily connect to configured MCP servers and list their tools.
- `shutdown_mcp_servers()` — Close all MCP server connections and stop the background loop.

### `tools/memory_tool.py`

_Memory Tool Module - Persistent Curated Memory_

**Classes:**

- **`MemoryStore`** — Bounded curated memory with file persistence. One instance per AIAgent.
  - `__init__(self, memory_char_limit: int, user_char_limit: int)`
  - `load_from_disk(self)`
  - `save_to_disk(self, target: str)`
  - `add(self, target: str, content: str) -> Dict[str, Any]`
  - `replace(self, target: str, old_text: str, new_content: str) -> Dict[str, Any]`
  - `remove(self, target: str, old_text: str) -> Dict[str, Any]`
  - `format_for_system_prompt(self, target: str) -> Optional[str]`

**Functions:**

- `get_memory_dir() -> Path` — Return the profile-scoped memories directory.
- `memory_tool(action: str, target: str, content: str, old_text: str, store: Optional[MemoryStore]) -> str` — Single entry point for the memory tool. Dispatches to MemoryStore methods.
- `check_memory_requirements() -> bool` — Memory tool has no external requirements -- always available.

### `tools/mixture_of_agents_tool.py`

_Mixture-of-Agents Tool Module_

**Functions:**

- `mixture_of_agents_tool(user_prompt: str, reference_models: Optional[List[str]], aggregator_model: Optional[str]) -> str` — Process a complex query using the Mixture-of-Agents methodology.
- `check_moa_requirements() -> bool` — Check if all requirements for MoA tools are met.
- `get_moa_configuration() -> Dict[str, Any]` — Get the current MoA configuration settings.

### `tools/neutts_synth.py`

_Standalone NeuTTS synthesis helper._

**Functions:**

- `main()`

### `tools/opencli_tool.py`

_OpenCLI tool for VectorCode — web research without API keys._

**Classes:**

- **`OpenCLITool`** — VectorCode web research tool wrapping OpenCLI + fallback scrapers.
  - `__init__(self, timeout: int) -> None`
  - `search(self, query: str, max_results: int) -> list[dict]`
  - `hn_top(self, limit: int) -> list[dict]`
  - `reddit_hot(self, subreddit: str, limit: int) -> list[dict]`
  - `github_trending(self, language: str, limit: int) -> list[dict]`
  - `twitter_trending(self, topic: str, limit: int) -> list[dict]`
  - `check_health(self) -> dict`
  - `format_results(self, results: list[dict]) -> str`

### `tools/openrouter_client.py`

_Shared OpenRouter API client for VectorCode tools._

**Functions:**

- `get_async_client()` — Return a shared async OpenAI-compatible client for OpenRouter.
- `check_api_key() -> bool` — Check whether the OpenRouter API key is present.

### `tools/osv_check.py`

_OSV malware check for MCP extension packages._

**Functions:**

- `check_package_for_malware(command: str, args: list) -> Optional[str]` — Check if an MCP server package has known malware advisories.

### `tools/patch_parser.py`

_V4A Patch Format Parser_

**Classes:**

- **`OperationType`**
- **`HunkLine`** — A single line in a patch hunk.
- **`Hunk`** — A group of changes within a file.
- **`PatchOperation`** — A single operation in a V4A patch.

**Functions:**

- `parse_v4a_patch(patch_content: str) -> Tuple[List[PatchOperation], Optional[str]]` — Parse a V4A format patch.
- `apply_v4a_operations(operations: List[PatchOperation], file_ops: Any) -> 'PatchResult'` — Apply V4A patch operations using a file operations interface.

### `tools/path_security.py`

_Shared path validation helpers for tool implementations._

**Functions:**

- `validate_within_dir(path: Path, root: Path) -> Optional[str]` — Ensure *path* resolves to a location within *root*.
- `has_traversal_component(path_str: str) -> bool` — Return True if *path_str* contains ``..`` traversal components.

### `tools/process_registry.py`

_Process Registry -- In-memory registry for managed background processes._

**Classes:**

- **`ProcessSession`** — A tracked background process with output buffering.
- **`ProcessRegistry`** — In-memory registry of running and finished background processes.
  - `__init__(self)`
  - `spawn_local(self, command: str, cwd: str, task_id: str, session_key: str, env_vars: dict, use_pty: bool) -> ProcessSession`
  - `spawn_via_env(self, env: Any, command: str, cwd: str, task_id: str, session_key: str, timeout: int) -> ProcessSession`
  - `is_completion_consumed(self, session_id: str) -> bool`
  - `get(self, session_id: str) -> Optional[ProcessSession]`
  - `poll(self, session_id: str) -> dict`
  - `read_log(self, session_id: str, offset: int, limit: int) -> dict`
  - `wait(self, session_id: str, timeout: int) -> dict`
  - _(+9 more methods)_

**Functions:**

- `format_uptime_short(seconds: int) -> str`

### `tools/registry.py`

_Central registry for all vectorcode tools._

**Classes:**

- **`ToolEntry`** — Metadata for a single registered tool.
  - `__init__(self, name, toolset, schema, handler, check_fn, requires_env, is_async, description, emoji, max_result_size_chars)`
- **`ToolRegistry`** — Singleton registry that collects tool schemas + handlers from tool files.
  - `__init__(self)`
  - `get_entry(self, name: str) -> Optional[ToolEntry]`
  - `get_registered_toolset_names(self) -> List[str]`
  - `get_tool_names_for_toolset(self, toolset: str) -> List[str]`
  - `register_toolset_alias(self, alias: str, toolset: str) -> None`
  - `get_registered_toolset_aliases(self) -> Dict[str, str]`
  - `get_toolset_alias_target(self, alias: str) -> Optional[str]`
  - `register(self, name: str, toolset: str, schema: dict, handler: Callable, check_fn: Callable, requires_env: list, is_async: bool, description: str, emoji: str, max_result_size_chars: int | float | None)`
  - _(+14 more methods)_

**Functions:**

- `discover_builtin_tools(tools_dir: Optional[Path]) -> List[str]` — Import built-in self-registering tool modules and return their module names.
- `tool_error(message) -> str` — Return a JSON error string for tool handlers.
- `tool_result(data) -> str` — Return a JSON result string for tool handlers.

### `tools/rl_training_tool.py`

_RL Training Tools Module_

**Classes:**

- **`EnvironmentInfo`** — Information about a discovered environment.
- **`RunState`** — State for a training run.

**Functions:**

- `rl_list_environments() -> str` — List all available RL environments.
- `rl_select_environment(name: str) -> str` — Select an RL environment for training.
- `rl_get_current_config() -> str` — Get the current environment configuration.
- `rl_edit_config(field: str, value: Any) -> str` — Update a configuration field.
- `rl_start_training() -> str` — Start a new RL training run with the current environment and config.
- `rl_check_status(run_id: str) -> str` — Get status and metrics for a training run.
- `rl_stop_training(run_id: str) -> str` — Stop a running training job.
- `rl_get_results(run_id: str) -> str` — Get final results and metrics for a training run.
- `rl_list_runs() -> str` — List all training runs (active and completed).
- `rl_test_inference(num_steps: int, group_size: int, models: Optional[List[str]]) -> str` — Quick inference test for any environment using Atropos's `process` mode.
- `check_rl_python_version() -> bool` — Check if Python version meets the minimum for RL tools.
- `check_rl_api_keys() -> bool` — Check if required API keys and Python version are available.
- `get_missing_keys() -> List[str]` — Get list of missing requirements for RL tools (API keys and Python version).

### `tools/schema_sanitizer.py`

_Sanitize tool JSON schemas for broad LLM-backend compatibility._

**Functions:**

- `sanitize_tool_schemas(tools: list[dict]) -> list[dict]` — Return a copy of ``tools`` with each tool's parameter schema sanitized.

### `tools/send_message_tool.py`

_Send Message Tool -- cross-channel messaging via platform APIs._

**Functions:**

- `send_message_tool(args)` — Handle cross-channel send_message tool calls.

### `tools/session_search_tool.py`

_Session Search Tool - Long-Term Conversation Recall_

**Functions:**

- `session_search(query: str, role_filter: str, limit: int, db, current_session_id: str) -> str` — Search past sessions and return focused summaries of matching conversations.
- `check_session_search_requirements() -> bool` — Requires SQLite state database and an auxiliary text model.

### `tools/skill_manager_tool.py`

_Skill Manager Tool -- Agent-Managed Skill Creation & Editing_

**Functions:**

- `skill_manage(action: str, name: str, content: str, category: str, file_path: str, file_content: str, old_string: str, new_string: str, replace_all: bool) -> str` — Manage user-created skills. Dispatches to the appropriate action handler.

### `tools/skills_guard.py`

_Skills Guard — Security scanner for externally-sourced skills._

**Classes:**

- **`Finding`**
- **`ScanResult`**

**Functions:**

- `scan_file(file_path: Path, rel_path: str) -> List[Finding]` — Scan a single file for threat patterns and invisible unicode characters.
- `scan_skill(skill_path: Path, source: str) -> ScanResult` — Scan all files in a skill directory for security threats.
- `should_allow_install(result: ScanResult, force: bool) -> Tuple[bool, str]` — Determine whether a skill should be installed based on scan result and trust.
- `format_scan_report(result: ScanResult) -> str` — Format a scan result as a human-readable report string.
- `content_hash(skill_path: Path) -> str` — Compute a SHA-256 hash of all files in a skill directory for integrity tracking.

### `tools/skills_hub.py`

_Skills Hub — Source adapters and hub state management for the VectorCode Skills Hub._

**Classes:**

- **`SkillMeta`** — Minimal metadata returned by search results.
- **`SkillBundle`** — A downloaded skill ready for quarantine/scanning/installation.
- **`GitHubAuth`** — GitHub API authentication. Tries methods in priority order:
  - `__init__(self)`
  - `get_headers(self) -> Dict[str, str]`
  - `is_authenticated(self) -> bool`
  - `auth_method(self) -> str`
- **`SkillSource`** — Abstract base for all skill registry adapters.
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
- **`GitHubSource`** — Fetch skills from GitHub repos via the Contents API.
  - `__init__(self, auth: GitHubAuth, extra_taps: Optional[List[Dict]])`
  - `source_id(self) -> str`
  - `is_rate_limited(self) -> bool`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
- **`WellKnownSkillSource`** — Read skills from a domain exposing /.well-known/skills/index.json.
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
- **`UrlSource`** — Fetch a single-file SKILL.md skill directly from an HTTP(S) URL.
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
- **`SkillsShSource`** — Discover skills via skills.sh and fetch content from the underlying GitHub repo.
  - `__init__(self, auth: GitHubAuth)`
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
- **`ClawHubSource`** — Fetch skills from ClawHub (clawhub.ai) via their HTTP API.
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
- **`ClaudeMarketplaceSource`** — Discover skills from Claude Code marketplace repos.
  - `__init__(self, auth: GitHubAuth)`
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
- **`LobeHubSource`** — Fetch skills from LobeHub's agent marketplace (14,500+ agents).
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
- **`OptionalSkillSource`** — Fetch skills from the optional-skills/ directory shipped with the repo.
  - `__init__(self)`
  - `source_id(self) -> str`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`
- **`HubLockFile`** — Manages skills/.hub/lock.json — tracks provenance of installed hub skills.
  - `__init__(self, path: Path)`
  - `load(self) -> dict`
  - `save(self, data: dict) -> None`
  - `record_install(self, name: str, source: str, identifier: str, trust_level: str, scan_verdict: str, skill_hash: str, install_path: str, files: List[str], metadata: Optional[Dict[str, Any]]) -> None`
  - `record_uninstall(self, name: str) -> None`
  - `get_installed(self, name: str) -> Optional[dict]`
  - `list_installed(self) -> List[dict]`
- **`TapsManager`** — Manages the taps.json file — custom GitHub repo sources.
  - `__init__(self, path: Path)`
  - `load(self) -> List[dict]`
  - `save(self, taps: List[dict]) -> None`
  - `add(self, repo: str, path: str) -> bool`
  - `remove(self, repo: str) -> bool`
  - `list_taps(self) -> List[dict]`
- **`VectorCodeIndexSource`** — Skill source backed by the centralized VectorCode Skills Index.
  - `__init__(self, auth: GitHubAuth)`
  - `source_id(self) -> str`
  - `is_available(self) -> bool`
  - `trust_level_for(self, identifier: str) -> str`
  - `search(self, query: str, limit: int) -> List[SkillMeta]`
  - `fetch(self, identifier: str) -> Optional[SkillBundle]`
  - `inspect(self, identifier: str) -> Optional[SkillMeta]`

**Functions:**

- `append_audit_log(action: str, skill_name: str, source: str, trust_level: str, verdict: str, extra: str) -> None` — Append a line to the audit log.
- `ensure_hub_dirs() -> None` — Create the .hub directory structure if it doesn't exist.
- `quarantine_bundle(bundle: SkillBundle) -> Path` — Write a skill bundle to the quarantine directory for scanning.
- `install_from_quarantine(quarantine_path: Path, skill_name: str, category: str, bundle: SkillBundle, scan_result: ScanResult) -> Path` — Move a scanned skill from quarantine into the skills directory.
- `uninstall_skill(skill_name: str) -> Tuple[bool, str]` — Remove a hub-installed skill. Refuses to remove builtins.
- `bundle_content_hash(bundle: SkillBundle) -> str` — Compute a deterministic hash for an in-memory skill bundle.
- `check_for_skill_updates(name: Optional[str], lock: Optional[HubLockFile], sources: Optional[List[SkillSource]], auth: Optional[GitHubAuth]) -> List[dict]` — Check installed hub skills for upstream changes.
- `create_source_router(auth: Optional[GitHubAuth]) -> List[SkillSource]` — Create all configured source adapters.
- `parallel_search_sources(sources: List[SkillSource], query: str, per_source_limits: Optional[Dict[str, int]], source_filter: str, overall_timeout: float, on_source_done: Optional[Any]) -> Tuple[List[SkillMeta], Dict[str, int], List[str]]` — Search all sources in parallel with per-source timeout.
- `unified_search(query: str, sources: List[SkillSource], source_filter: str, limit: int) -> List[SkillMeta]` — Search all sources (in parallel) and merge results.

### `tools/skills_sync.py`

_Skills Sync -- Manifest-based seeding and updating of bundled skills._

**Functions:**

- `sync_skills(quiet: bool) -> dict` — Sync bundled skills into ~/.vectorcode/skills/ using the manifest.
- `reset_bundled_skill(name: str, restore: bool) -> dict` — Reset a bundled skill's manifest tracking so future syncs work normally.

### `tools/skills_tool.py`

_Skills Tool Module_

**Classes:**

- **`SkillReadinessStatus`**

**Functions:**

- `load_env() -> Dict[str, str]` — Load profile-scoped environment variables from VECTOR_HOME/.env.
- `set_secret_capture_callback(callback) -> None`
- `skill_matches_platform(frontmatter: Dict[str, Any]) -> bool` — Check if a skill is compatible with the current OS platform.
- `check_skills_requirements() -> bool` — Skills are always available -- the directory is created on first use if needed.
- `skills_list(category: str, task_id: str) -> str` — List all available skills (progressive disclosure tier 1 - minimal metadata).
- `skill_view(name: str, file_path: str, task_id: str, preprocess: bool) -> str` — View the content of a skill or a specific file within a skill directory.

### `tools/stt_tool.py`

_STT tool — speech-to-text transcription with multiple providers._

**Functions:**

- `transcribe_audio(audio_path: str, provider: str, language: str) -> dict` — Transcribe audio file to text.

### `tools/terminal.py`

_Terminal tool — execute shell commands with approval gate._

**Functions:**

- `set_approval_callback(fn: Optional[Callable]) -> None`
- `bash(command: str, timeout: int, cwd: Optional[str], description: Optional[str]) -> str` — Execute a shell command and return its output.

### `tools/terminal_tool.py`

_Terminal Tool Module_

**Functions:**

- `set_sudo_password_callback(cb)` — Register a callback for sudo password prompts (used by CLI).
- `set_approval_callback(cb)` — Register a callback for dangerous command approval prompts.
- `register_task_env_overrides(task_id: str, overrides: Dict[str, Any])` — Register environment overrides for a specific task/rollout.
- `clear_task_env_overrides(task_id: str)` — Clear environment overrides for a task after rollout completes.
- `get_active_env(task_id: str)` — Return the active BaseEnvironment for *task_id*, or None.
- `is_persistent_env(task_id: str) -> bool` — Return True if the active environment for task_id is configured for
- `cleanup_all_environments()` — Clean up ALL active environments. Use with caution.
- `cleanup_vm(task_id: str)` — Manually clean up a specific environment by task_id.
- `terminal_tool(command: str, background: bool, timeout: Optional[int], task_id: Optional[str], force: bool, workdir: Optional[str], pty: bool, notify_on_complete: bool, watch_patterns: Optional[List[str]]) -> str` — Execute a command in the configured terminal environment.
- `check_terminal_requirements() -> bool` — Check if all requirements for the terminal tool are met.

### `tools/tirith_security.py`

_Tirith pre-exec security scanning wrapper._

**Functions:**

- `ensure_installed(log_failures: bool)` — Ensure tirith is available, downloading in background if needed.
- `check_command_security(command: str) -> dict` — Run tirith security scan on a command.

### `tools/todo_tool.py`

_Todo Tool Module - Planning & Task Management_

**Classes:**

- **`TodoStore`** — In-memory todo list. One instance per AIAgent (one per session).
  - `__init__(self)`
  - `write(self, todos: List[Dict[str, Any]], merge: bool) -> List[Dict[str, str]]`
  - `read(self) -> List[Dict[str, str]]`
  - `has_items(self) -> bool`
  - `format_for_injection(self) -> Optional[str]`

**Functions:**

- `todo_tool(todos: Optional[List[Dict[str, Any]]], merge: bool, store: Optional[TodoStore]) -> str` — Single entry point for the todo tool. Reads or writes depending on params.
- `check_todo_requirements() -> bool` — Todo tool has no external requirements -- always available.

### `tools/tool_backend_helpers.py`

_Shared helpers for tool backend selection._

**Functions:**

- `managed_nous_tools_enabled() -> bool` — Return True when the user has an active paid Nous subscription.
- `normalize_browser_cloud_provider(value: object | None) -> str` — Return a normalized browser provider key.
- `coerce_modal_mode(value: object | None) -> str` — Return the requested modal mode when valid, else the default.
- `normalize_modal_mode(value: object | None) -> str` — Return a normalized modal execution mode.
- `has_direct_modal_credentials() -> bool` — Return True when direct Modal credentials/config are available.
- `resolve_modal_backend_state(modal_mode: object | None, has_direct: bool, managed_ready: bool) -> Dict[str, Any]` — Resolve direct vs managed Modal backend selection.
- `resolve_openai_audio_api_key() -> str` — Prefer the voice-tools key, but fall back to the normal OpenAI key.
- `prefers_gateway(config_section: str) -> bool` — Return True when the user opted into the Tool Gateway for this tool.
- `fal_key_is_configured() -> bool` — Return True when FAL_KEY is set to a non-whitespace value.

### `tools/tool_output_limits.py`

_Configurable tool-output truncation limits._

**Functions:**

- `get_tool_output_limits() -> Dict[str, int]` — Return resolved tool-output limits, reading ``tool_output`` from config.
- `get_max_bytes() -> int` — Shortcut for terminal-tool callers that only need the byte cap.
- `get_max_lines() -> int` — Shortcut for file-ops callers that only need the line cap.
- `get_max_line_length() -> int` — Shortcut for file-ops callers that only need the per-line cap.

### `tools/tool_result_storage.py`

_Tool result persistence -- preserves large outputs instead of truncating._

**Functions:**

- `generate_preview(content: str, max_chars: int) -> tuple[str, bool]` — Truncate at last newline within max_chars. Returns (preview, has_more).
- `maybe_persist_tool_result(content: str, tool_name: str, tool_use_id: str, env, config: BudgetConfig, threshold: int | float | None) -> str` — Layer 2: persist oversized result into the sandbox, return preview + path.
- `enforce_turn_budget(tool_messages: list[dict], env, config: BudgetConfig) -> list[dict]` — Layer 3: enforce aggregate budget across all tool results in a turn.

### `tools/toolset.py`

_Toolset manager — enable/disable groups of tools per session or task type._

**Classes:**

- **`ToolsetManager`** — Maintains the set of currently allowed tool names for the session.
  - `__init__(self) -> None`
  - `enable(self, toolset_name: str) -> dict`
  - `disable(self, toolset_name: str) -> None`
  - `add_tool(self, tool_name: str) -> None`
  - `remove_tool(self, tool_name: str) -> None`
  - `get_active_tools(self) -> set[str]`
  - `is_allowed(self, tool_name: str) -> bool`
  - `list_toolsets(self) -> dict[str, list[str]]`
  - _(+1 more methods)_

**Functions:**

- `get_toolset_manager() -> ToolsetManager` — Return the process-wide singleton ToolsetManager.

### `tools/transcription_tools.py`

_Transcription Tools Module_

**Functions:**

- `is_stt_enabled(stt_config: Optional[dict]) -> bool` — Return whether STT is enabled in config.
- `transcribe_audio(file_path: str, model: Optional[str]) -> Dict[str, Any]` — Transcribe an audio file using the configured STT provider.

### `tools/tts_tool.py`

_Text-to-Speech Tool Module_

**Functions:**

- `text_to_speech_tool(text: str, output_path: Optional[str]) -> str` — Convert text to speech audio.
- `check_tts_requirements() -> bool` — Check if at least one TTS provider is available.
- `stream_tts_to_speaker(text_queue: queue.Queue, stop_event: threading.Event, tts_done_event: threading.Event, display_callback: Optional[Callable[[str], None]])` — Consume text deltas from *text_queue*, buffer them into sentences,

### `tools/url_safety.py`

_URL safety checks — blocks requests to private/internal network addresses._

**Functions:**

- `is_safe_url(url: str) -> bool` — Return True if the URL target is not a private/internal address.

### `tools/vision_tools.py`

_Vision Tools Module_

**Functions:**

- `vision_analyze_tool(image_url: str, user_prompt: str, model: str) -> str` — Analyze an image from a URL or local file path using vision AI.
- `check_vision_requirements() -> bool` — Check if the configured runtime vision path can resolve a client.

### `tools/voice_mode.py`

_Voice Mode -- Push-to-talk audio recording and playback for the CLI._

**Classes:**

- **`TermuxAudioRecorder`** — Recorder backend that uses Termux:API microphone capture commands.
  - `__init__(self) -> None`
  - `is_recording(self) -> bool`
  - `elapsed_seconds(self) -> float`
  - `current_rms(self) -> int`
  - `start(self, on_silence_stop) -> None`
  - `stop(self) -> Optional[str]`
  - `cancel(self) -> None`
  - `shutdown(self) -> None`
- **`AudioRecorder`** — Thread-safe audio recorder using sounddevice.InputStream.
  - `__init__(self) -> None`
  - `elapsed_seconds(self) -> float`
  - `current_rms(self) -> int`
  - `is_recording(self) -> bool`
  - `start(self, on_silence_stop) -> None`
  - `stop(self) -> Optional[str]`
  - `cancel(self) -> None`
  - `shutdown(self) -> None`

**Functions:**

- `detect_audio_environment() -> dict` — Detect if the current environment supports audio I/O.
- `play_beep(frequency: int, duration: float, count: int) -> None` — Play a short beep tone using numpy + sounddevice.
- `create_audio_recorder() -> AudioRecorder | TermuxAudioRecorder` — Return the best recorder backend for the current environment.
- `is_whisper_hallucination(transcript: str) -> bool` — Check if a transcript is a known Whisper hallucination on silence.
- `transcribe_recording(wav_path: str, model: Optional[str]) -> Dict[str, Any]` — Transcribe a WAV recording using the existing Whisper pipeline.
- `stop_playback() -> None` — Interrupt the currently playing audio (if any).
- `play_audio_file(file_path: str) -> bool` — Play an audio file through the default output device.
- `check_voice_requirements() -> Dict[str, Any]` — Check if all voice mode requirements are met.
- `cleanup_temp_recordings(max_age_seconds: int) -> int` — Remove old temporary voice recording files.

### `tools/web_tools.py`

_Standalone Web Tools Module_

**Functions:**

- `process_content_with_llm(content: str, url: str, title: str, model: Optional[str], min_length: int) -> Optional[str]` — Process web content using LLM to create intelligent summaries with key excerpts.
- `clean_base64_images(text: str) -> str` — Remove base64 encoded images from text to reduce token count and clutter.
- `web_search_tool(query: str, limit: int) -> str` — Search the web for information using available search API backend.
- `web_extract_tool(urls: List[str], format: str, use_llm_processing: bool, model: Optional[str], min_length: int) -> str` — Extract content from specific web pages using available extraction API backend.
- `web_crawl_tool(url: str, instructions: str, depth: str, use_llm_processing: bool, model: Optional[str], min_length: int) -> str` — Crawl a website with specific instructions using available crawling API backend.
- `check_firecrawl_api_key() -> bool` — Check whether the Firecrawl backend is available.
- `check_web_api_key() -> bool` — Check whether the configured web backend is available.
- `check_auxiliary_model() -> bool` — Check if an auxiliary text model is available for LLM content processing.

### `tools/website_policy.py`

_Website access policy helpers for URL-capable tools._

**Classes:**

- **`WebsitePolicyError`** — Raised when a website policy file is malformed.

**Functions:**

- `load_website_blocklist(config_path: Optional[Path]) -> Dict[str, Any]` — Load and return the parsed website blocklist policy.
- `invalidate_cache() -> None` — Force the next ``check_website_access`` call to re-read config.
- `check_website_access(url: str, config_path: Optional[Path]) -> Optional[Dict[str, str]]` — Check whether a URL is allowed by the website blocklist policy.

### `tools/worktree.py`

_Git worktree isolation — create isolated copies for risky operations._

**Classes:**

- **`WorktreeManager`** — Create, manage, and remove git worktrees for isolated operations.
  - `__init__(self, repo_root: Path) -> None`
  - `create(self, branch_name: str, base: str) -> Path`
  - `destroy(self, worktree_path: Path) -> bool`
  - `list_worktrees(self) -> list[dict]`
  - `diff_from_main(self, worktree_path: Path) -> str`
  - `merge_to_main(self, worktree_path: Path, message: str) -> dict`
  - `cleanup_all(self) -> int`

### `tools/xai_http.py`

_Shared helpers for direct xAI HTTP integrations._

**Functions:**

- `vector_xai_user_agent() -> str` — Return a stable VectorCode-specific User-Agent for xAI HTTP calls.

### `tools/yuanbao_tools.py`

_yuanbao_tools.py - 元宝平台工具集_

**Functions:**

- `get_group_info(group_code: str) -> dict` — 查询群基本信息（群名、群主、成员数）。
- `query_group_members(group_code: str, action: str, name: str, mention: bool) -> dict` — 统一的群成员查询工具（对齐 TS query_session_members）。
- `search_sticker(query: str, limit: int) -> dict` — 在内置贴纸表中按关键词模糊搜索，返回 Top-N 候选。
- `send_sticker(sticker: str, chat_id: str, reply_to: str) -> dict` — 向 chat_id（缺省取当前会话）发送一张内置贴纸（TIMFaceElem）。
- `send_dm(group_code: str, name: str, message: str, user_id: str, media_files: Optional[List[Tuple[str, bool]]]) -> dict` — Send a DM (private chat message) to a group member, with optional media.


---

## (root)

### `toolset_distributions.py`

_Toolset Distributions Module_

**Functions:**

- `get_distribution(name: str) -> Optional[Dict[str, any]]` — Get a toolset distribution by name.
- `list_distributions() -> Dict[str, Dict]` — List all available distributions.
- `sample_toolsets_from_distribution(distribution_name: str) -> List[str]` — Sample toolsets based on a distribution's probabilities.
- `validate_distribution(distribution_name: str) -> bool` — Check if a distribution name is valid.
- `print_distribution_info(distribution_name: str) -> None` — Print detailed information about a distribution.


---

## (root)

### `toolsets.py`

_Toolsets Module_

**Functions:**

- `get_toolset(name: str) -> Optional[Dict[str, Any]]` — Get a toolset definition by name.
- `resolve_toolset(name: str, visited: Set[str]) -> List[str]` — Recursively resolve a toolset to get all tool names.
- `resolve_multiple_toolsets(toolset_names: List[str]) -> List[str]` — Resolve multiple toolsets and combine their tools.
- `get_all_toolsets() -> Dict[str, Dict[str, Any]]` — Get all available toolsets with their definitions.
- `get_toolset_names() -> List[str]` — Get names of all available toolsets (excluding aliases).
- `validate_toolset(name: str) -> bool` — Check if a toolset name is valid.
- `create_custom_toolset(name: str, description: str, tools: List[str], includes: List[str]) -> None` — Create a custom toolset at runtime.
- `get_toolset_info(name: str) -> Dict[str, Any]` — Get detailed information about a toolset including resolved tools.


---

## (root)

### `trajectory_compressor.py`

_Trajectory Compressor_

**Classes:**

- **`CompressionConfig`** — Configuration for trajectory compression.
  - `from_yaml(cls, yaml_path: str) -> 'CompressionConfig'`
- **`TrajectoryMetrics`** — Metrics for a single trajectory compression.
  - `to_dict(self) -> Dict[str, Any]`
- **`AggregateMetrics`** — Aggregate metrics across all trajectories.
  - `add_trajectory_metrics(self, metrics: TrajectoryMetrics)`
  - `to_dict(self) -> Dict[str, Any]`
- **`TrajectoryCompressor`** — Compresses agent trajectories to fit within a target token budget.
  - `__init__(self, config: CompressionConfig)`
  - `count_tokens(self, text: str) -> int`
  - `count_trajectory_tokens(self, trajectory: List[Dict[str, str]]) -> int`
  - `count_turn_tokens(self, trajectory: List[Dict[str, str]]) -> List[int]`
  - `compress_trajectory(self, trajectory: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], TrajectoryMetrics]`
  - `compress_trajectory_async(self, trajectory: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], TrajectoryMetrics]`
  - `process_entry_async(self, entry: Dict[str, Any]) -> Tuple[Dict[str, Any], TrajectoryMetrics]`
  - `process_entry(self, entry: Dict[str, Any]) -> Tuple[Dict[str, Any], TrajectoryMetrics]`
  - _(+1 more methods)_

**Functions:**

- `main(input: str, output: str, config: str, target_max_tokens: int, tokenizer: str, sample_percent: float, seed: int, dry_run: bool)` — Compress agent trajectories to fit within a target token budget.


---

## transports

### `transports/anthropic.py`

_Anthropic Messages API transport for VectorCode._

**Classes:**

- **`AnthropicTransport`** — Transport for api_mode='anthropic_messages'.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> tuple`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]`
  - `map_finish_reason(self, raw_reason: str) -> str`
  - _(+1 more methods)_

**Functions:**

- `apply_anthropic_cache_control(api_messages: List[Dict[str, Any]], cache_ttl: str, native_anthropic: bool) -> List[Dict[str, Any]]` — Apply system_and_3 caching strategy to messages for Anthropic models.

### `transports/base.py`

_Abstract base for provider transports._

**Classes:**

- **`ProviderTransport`** — Base class for provider-specific format conversion and normalization.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> Any`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> Any`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]`
  - `map_finish_reason(self, raw_reason: str) -> str`
  - _(+1 more methods)_

### `transports/chat_completions.py`

_OpenAI Chat Completions transport for VectorCode._

**Classes:**

- **`ChatCompletionsTransport`** — Transport for api_mode='chat_completions'.
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]`

### `transports/ollama.py`

_Ollama transport for VectorCode._

**Classes:**

- **`OllamaTransport`** — Transport for api_mode='ollama'.
  - `__init__(self, host: str) -> None`
  - `api_mode(self) -> str`
  - `convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `build_kwargs(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `normalize_response(self, response: Any) -> NormalizedResponse`
  - `validate_response(self, response: Any) -> bool`
  - `complete_streaming(self, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> NormalizedResponse`

### `transports/types.py`

_Shared types for normalized provider responses._

**Classes:**

- **`Usage`** — Token usage from an API response.
- **`ToolCall`** — A normalized tool call from any provider.
  - `type(self) -> str`
  - `function(self) -> 'ToolCall'`
  - `call_id(self) -> Optional[str]`
  - `response_item_id(self) -> Optional[str]`
  - `extra_content(self) -> Optional[Dict[str, Any]]`
- **`NormalizedResponse`** — Normalized API response from any provider.
  - `reasoning_content(self) -> Optional[str]`
  - `reasoning_details(self)`
  - `codex_reasoning_items(self)`
  - `codex_message_items(self)`

**Functions:**

- `build_tool_call(id: Optional[str], name: str, arguments: Any, provider_data: Optional[Dict[str, Any]]) -> ToolCall` — Build a ToolCall, auto-serialising arguments if it is a dict.
- `map_finish_reason(raw: Optional[str], provider: str) -> str` — Translate a provider-specific stop reason to the normalised set.


---

## utils

### `utils/core.py`

_Core utility functions for VectorCode._

**Functions:**

- `is_truthy_value(value: Any, default: bool) -> bool`
- `env_var_enabled(name: str, default: str) -> bool` — Return True when an environment variable is set to a truthy value.
- `env_int(key: str, default: int) -> int`
- `safe_json_loads(text: str, default: Any) -> Any` — Parse JSON, returning default on any parse error.
- `atomic_json_write(path: Union[str, Path], data: Any, indent: int) -> None` — Write JSON data to a file atomically (temp + fsync + os.replace).
- `normalize_proxy_url(proxy_url: Optional[str]) -> Optional[str]` — Normalize proxy URLs (socks:// → socks5://).
- `base_url_hostname(base_url: str) -> str` — Return the lowercased hostname for a base URL.
- `base_url_host_matches(base_url: str, domain: str) -> bool` — Return True when the base URL's hostname is domain or a subdomain.

### `utils/logging.py`

_Structured logging — per-subsystem log levels, file rotation, JSON output._

**Classes:**

- **`LogLevel`**
- **`LogConfig`**
- **`VectorLogger`** — Per-subsystem logger wrapping loguru.
  - `__init__(self, subsystem: str, config: LogConfig) -> None`
  - `set_session_id(self, session_id: str) -> None`
  - `set_level(self, level: LogLevel) -> None`
  - `trace(self, msg: str) -> None`
  - `debug(self, msg: str) -> None`
  - `info(self, msg: str) -> None`
  - `success(self, msg: str) -> None`
  - `warning(self, msg: str) -> None`
  - _(+2 more methods)_
- **`LogManager`** — Central log manager.  Configures loguru sinks and manages per-subsystem loggers.
  - `configure(cls, config: LogConfig) -> None`
  - `set_subsystem_level(cls, subsystem: str, level: LogLevel) -> None`
  - `get_logger(cls, subsystem: str) -> 'VectorLogger'`
  - `reset(cls) -> None`

**Functions:**

- `get_subsystem_logger(subsystem: str) -> VectorLogger` — Convenience: get logger for a subsystem.
- `configure_logging(level: str, json_format: bool, log_dir: Optional[Path], rotation: str, retention: str) -> None` — One-call logging setup.  Call at startup.

### `utils/reasoning_stripper.py`

_Strip <think>...</think> and <REASONING_SCRATCHPAD>...</REASONING_SCRATCHPAD> tags_

**Functions:**

- `strip_reasoning(text: str) -> str` — Remove <think> and <REASONING_SCRATCHPAD> blocks from *text*.
- `extract_reasoning(text: str) -> tuple[str, str]` — Return (clean_text, reasoning_content).
- `has_incomplete_reasoning(text: str) -> bool` — Return True if the text contains an opening <think> without a closing </think>.
- `convert_scratchpad_to_think(text: str) -> str` — Replace REASONING_SCRATCHPAD tags with think tags.

### `utils/redact.py`

_Output redaction — strip sensitive data from model outputs._

**Functions:**

- `redact(text: str, preserve_urls: bool, preserve_emails: bool) -> str`
- `redact_dict(data: dict, keys_to_redact: Optional[list[str]]) -> dict`

### `utils/subdirectory_hints.py`

_SubdirectoryHintTracker — tracks explored paths, suggests unexplored areas._

**Classes:**

- **`SubdirStats`**
- **`SubdirectoryHintTracker`** — Tracks which subdirectories the agent has accessed during a session.
  - `__init__(self, project_dir: str, max_depth: int, top_k: int) -> None`
  - `on_file_access(self, file_path: str) -> None`
  - `get_hints(self, max_hints: int) -> list[str]`
  - `get_visited_summary(self) -> dict`
  - `reset(self) -> None`

**Functions:**

- `get_hint_tracker(project_dir: str) -> SubdirectoryHintTracker` — Return a per-project singleton SubdirectoryHintTracker.

### `utils/time_utils.py`

_Timezone-aware clock for VectorCode._

**Functions:**

- `get_timezone() -> Optional['ZoneInfo']`
- `now() -> datetime` — Return current time as a timezone-aware datetime.
- `reset_cache() -> None` — Force re-resolution of timezone on next call.
- `format_duration(seconds: float) -> str` — Format a duration in seconds as a human-readable string.
- `parse_relative_time(text: str) -> Optional[datetime]` — Parse relative time strings like '5m', '2h', '1d' into a future datetime.

### `utils/title_generator.py`

_Title generator — generate session titles from conversation content._

**Functions:**

- `generate_title(messages: list[dict], max_words: int) -> str` — Generate a title from the first user message.

### `utils/usage_pricing.py`

_Usage pricing — track and display token cost per session._

**Functions:**

- `record_usage(model: str, input_tokens: int, output_tokens: int, cost: float)`
- `get_usage_summary(days: Optional[int]) -> dict`


---

## (root)

### `utils.py`

_Shared utility functions for vectorcode._

**Functions:**

- `is_truthy_value(value: Any, default: bool) -> bool` — Coerce bool-ish values using the project's shared truthy string set.
- `env_var_enabled(name: str, default: str) -> bool` — Return True when an environment variable is set to a truthy value.
- `atomic_json_write(path: Union[str, Path], data: Any, indent: int) -> None` — Write JSON data to a file atomically.
- `atomic_yaml_write(path: Union[str, Path], data: Any, default_flow_style: bool, sort_keys: bool, extra_content: str | None) -> None` — Write YAML data to a file atomically.
- `safe_json_loads(text: str, default: Any) -> Any` — Parse JSON, returning *default* on any parse error.
- `env_int(key: str, default: int) -> int` — Read an environment variable as an integer, with fallback.
- `env_bool(key: str, default: bool) -> bool` — Read an environment variable as a boolean.
- `normalize_proxy_url(proxy_url: str | None) -> str | None` — Normalize proxy URLs for httpx/aiohttp compatibility.
- `normalize_proxy_env_vars() -> None` — Rewrite supported proxy env vars to canonical URL forms in-place.
- `base_url_hostname(base_url: str) -> str` — Return the lowercased hostname for a base URL, or ``""`` if absent.
- `base_url_host_matches(base_url: str, domain: str) -> bool` — Return True when the base URL's hostname is ``domain`` or a subdomain.


---

## vector_cli

### `vector_cli/auth.py`

_Multi-provider authentication system for VectorCode._

**Classes:**

- **`ProviderConfig`** — Describes a known inference provider.
- **`AuthError`** — Structured auth error with UX mapping hints.
  - `__init__(self, message: str, provider: str, code: Optional[str], relogin_required: bool) -> None`

**Functions:**

- `get_anthropic_key() -> str` — Return the first usable Anthropic credential, or ``""``.
- `has_usable_secret(value: Any, min_length: int) -> bool` — Return True when a configured secret looks usable, not empty/placeholder.
- `detect_zai_endpoint(api_key: str, timeout: float) -> Optional[Dict[str, str]]` — Probe z.ai endpoints to find one that accepts this API key.
- `format_auth_error(error: Exception) -> str` — Map auth failures to concise user-facing guidance.
- `is_known_auth_provider(provider_id: str) -> bool`
- `get_auth_provider_display_name(provider_id: str) -> str`
- `read_credential_pool(provider_id: Optional[str]) -> Dict[str, Any]` — Return the persisted credential pool, or one provider slice.
- `write_credential_pool(provider_id: str, entries: List[Dict[str, Any]]) -> Path` — Persist one provider's credential pool under auth.json.
- `suppress_credential_source(provider_id: str, source: str) -> None` — Mark a credential source as suppressed so it won't be re-seeded.
- `is_source_suppressed(provider_id: str, source: str) -> bool` — Check if a credential source has been suppressed by the user.
- `unsuppress_credential_source(provider_id: str, source: str) -> bool` — Clear a suppression marker so the source will be re-seeded on the next load.
- `get_provider_auth_state(provider_id: str) -> Optional[Dict[str, Any]]` — Return persisted auth state for a provider, or None.
- `get_active_provider() -> Optional[str]` — Return the currently active provider ID from auth store.
- `is_provider_explicitly_configured(provider_id: str) -> bool` — Return True only if the user has explicitly configured this provider.
- `clear_provider_auth(provider_id: Optional[str]) -> bool` — Clear auth state for a provider. Used by `vector logout`.
- _(+26 more functions)_

### `vector_cli/auth_commands.py`

_Credential-pool auth subcommands._

**Functions:**

- `auth_add_command(args) -> None`
- `auth_list_command(args) -> None`
- `auth_remove_command(args) -> None`
- `auth_reset_command(args) -> None`
- `auth_status_command(args) -> None`
- `auth_logout_command(args) -> None`
- `auth_spotify_command(args) -> None`
- `auth_command(args) -> None`

### `vector_cli/azure_detect.py`

_Azure Foundry endpoint auto-detection._

**Classes:**

- **`DetectionResult`** — Everything auto-detection could gather from a base URL + API key.

**Functions:**

- `detect(base_url: str, api_key: str) -> DetectionResult` — Inspect an Azure endpoint and describe its transport + models.
- `lookup_context_length(model: str, base_url: str, api_key: str) -> Optional[int]` — Thin wrapper around :func:`agent.model_metadata.get_model_context_length`

### `vector_cli/backup.py`

_Backup and import commands for vector CLI._

**Functions:**

- `run_backup(args) -> None` — Create a zip backup of the VectorCode home directory.
- `run_import(args) -> None` — Restore a VectorCode backup from a zip file.
- `create_quick_snapshot(label: Optional[str], vector_home: Optional[Path]) -> Optional[str]` — Create a quick state snapshot of critical files.
- `list_quick_snapshots(limit: int, vector_home: Optional[Path]) -> List[Dict[str, Any]]` — List existing quick state snapshots, most recent first.
- `restore_quick_snapshot(snapshot_id: str, vector_home: Optional[Path]) -> bool` — Restore state from a quick snapshot.
- `prune_quick_snapshots(keep: int, vector_home: Optional[Path]) -> int` — Manually prune quick snapshots. Returns count deleted.
- `run_quick_backup(args) -> None` — CLI entry point for vector backup --quick.
- `create_pre_update_backup(vector_home: Optional[Path], keep: int) -> Optional[Path]` — Create a full zip backup of VECTOR_HOME under ``backups/``.

### `vector_cli/banner.py`

_Welcome banner, ASCII art, skills summary, and update check for the CLI._

**Functions:**

- `cprint(text: str)` — Print ANSI-colored text through prompt_toolkit's renderer.
- `get_available_skills() -> Dict[str, List[str]]` — Return skills grouped by category, filtered by platform and disabled state.
- `check_for_updates() -> Optional[int]` — Check how many commits behind origin/main the local repo is.
- `get_git_banner_state(repo_dir: Optional[Path]) -> Optional[dict]` — Return upstream/local git hashes for the startup banner.
- `get_latest_release_tag(repo_dir: Optional[Path]) -> Optional[tuple]` — Return ``(tag, release_url)`` for the latest git tag, or None.
- `format_banner_version_label() -> str` — Return the version label shown in the startup banner title.
- `prefetch_update_check()` — Kick off update check in a background daemon thread.
- `get_update_result(timeout: float) -> Optional[int]` — Get result of prefetched check. Returns None if not ready.
- `build_welcome_banner(console: Console, model: str, cwd: str, tools: List[dict], enabled_toolsets: List[str], session_id: str, get_toolset_for_tool, context_length: int)` — Build and print a welcome banner with caduceus on left and info on right.

### `vector_cli/callbacks.py`

_Interactive prompt callbacks for terminal_tool integration._

**Functions:**

- `clarify_callback(cli, question, choices)` — Prompt for clarifying question through the TUI.
- `prompt_for_secret(cli, var_name: str, prompt: str, metadata) -> dict` — Prompt for a secret value through the TUI (e.g. API keys for skills).
- `approval_callback(cli, command: str, description: str) -> str` — Prompt for dangerous command approval through the TUI.

### `vector_cli/claw.py`

_vector claw — OpenClaw migration commands._

**Functions:**

- `claw_command(args)` — Route vector claw subcommands.

### `vector_cli/cli_output.py`

_Shared CLI output helpers for VectorCode CLI modules._

**Functions:**

- `print_info(text: str) -> None` — Print a dim informational message.
- `print_success(text: str) -> None` — Print a green success message with ✓ prefix.
- `print_warning(text: str) -> None` — Print a yellow warning message with ⚠ prefix.
- `print_error(text: str) -> None` — Print a red error message with ✗ prefix.
- `print_header(text: str) -> None` — Print a bold yellow header.
- `prompt(question: str, default: str | None, password: bool) -> str` — Prompt the user for input with optional default and password masking.
- `prompt_yes_no(question: str, default: bool) -> bool` — Prompt for a yes/no answer. Returns bool.

### `vector_cli/clipboard.py`

_Clipboard image extraction for macOS, Windows, Linux, and WSL2._

**Functions:**

- `save_clipboard_image(dest: Path) -> bool` — Extract an image from the system clipboard and save it as PNG.
- `has_clipboard_image() -> bool` — Quick check: does the clipboard currently contain an image?

### `vector_cli/codex_models.py`

_Codex model discovery from API, local cache, and config._

**Functions:**

- `get_codex_model_ids(access_token: Optional[str]) -> List[str]` — Return available Codex model IDs, trying API first, then local sources.

### `vector_cli/colors.py`

_Shared ANSI color utilities for VectorCode CLI modules._

**Classes:**

- **`Colors`**

**Functions:**

- `should_use_color() -> bool` — Return True when colored output is appropriate.
- `color(text: str) -> str` — Apply color codes to text (only when color output is appropriate).

### `vector_cli/commands.py`

_Slash command definitions and autocomplete for the VectorCode CLI._

**Classes:**

- **`CommandDef`** — Definition of a single slash command.
- **`SlashCommandCompleter`** — Autocomplete for built-in slash commands, subcommands, and skill commands.
  - `__init__(self, skill_commands_provider: Callable[[], Mapping[str, dict[str, Any]]] | None, command_filter: Callable[[str], bool] | None) -> None`
  - `get_completions(self, document, complete_event)`
- **`SlashCommandAutoSuggest`** — Inline ghost-text suggestions for slash commands and their subcommands.
  - `__init__(self, history_suggest: AutoSuggest | None, completer: SlashCommandCompleter | None) -> None`
  - `get_suggestion(self, buffer, document)`

**Functions:**

- `resolve_command(name: str) -> CommandDef | None` — Resolve a command name or alias to its CommandDef.
- `is_gateway_known_command(name: str | None) -> bool` — Return True if ``name`` resolves to a gateway-dispatchable slash command.
- `should_bypass_active_session(command_name: str | None) -> bool` — Return True for any resolvable slash command.
- `gateway_help_lines() -> list[str]` — Generate gateway help text lines from the registry.
- `telegram_bot_commands() -> list[tuple[str, str]]` — Return (command_name, description) pairs for Telegram setMyCommands.
- `telegram_menu_commands(max_commands: int) -> tuple[list[tuple[str, str]], int]` — Return Telegram menu commands capped to the Bot API limit.
- `discord_skill_commands(max_slots: int, reserved_names: set[str]) -> tuple[list[tuple[str, str, str]], int]` — Return skill entries for Discord slash command registration.
- `discord_skill_commands_by_category(reserved_names: set[str]) -> tuple[dict[str, list[tuple[str, str, str]]], list[tuple[str, str, str]], int]` — Return skill entries organized by category for Discord ``/skill`` subcommand groups.
- `slack_native_slashes() -> list[tuple[str, str, str]]` — Return (slash_name, description, usage_hint) triples for Slack.
- `slack_app_manifest(request_url: str) -> dict[str, Any]` — Generate a Slack app manifest with all gateway commands as slashes.
- `slack_subcommand_map() -> dict[str, str]` — Return subcommand -> /command mapping for Slack /vector handler.

### `vector_cli/completion.py`

_Shell completion script generation for vector CLI._

**Functions:**

- `generate_bash(parser: argparse.ArgumentParser) -> str`
- `generate_zsh(parser: argparse.ArgumentParser) -> str`
- `generate_fish(parser: argparse.ArgumentParser) -> str`

### `vector_cli/config.py`

_Configuration management for VectorCode._

**Classes:**

- **`ConfigIssue`** — A detected config structure problem.

**Functions:**

- `get_managed_system() -> Optional[str]` — Return the package manager owning this install, if any.
- `is_managed() -> bool` — Check if VectorCode is running in package-manager-managed mode.
- `get_managed_update_command() -> Optional[str]` — Return the preferred upgrade command for a managed install.
- `recommended_update_command() -> str` — Return the best update command for the current installation.
- `format_managed_message(action: str) -> str` — Build a user-facing error for managed installs.
- `managed_error(action: str)` — Print user-friendly error for managed mode.
- `get_container_exec_info() -> Optional[dict]` — Read container mode metadata from VECTOR_HOME/.container-mode.
- `get_config_path() -> Path` — Get the main config file path.
- `get_env_path() -> Path` — Get the .env file path (for API keys).
- `get_project_root() -> Path` — Get the project installation directory.
- `ensure_vector_home()` — Ensure ~/.vectorcode directory structure exists with secure permissions.
- `get_missing_env_vars(required_only: bool) -> List[Dict[str, Any]]` — Check which environment variables are missing.
- `get_missing_config_fields() -> List[Dict[str, Any]]` — Check which config fields are missing or outdated (recursive).
- `get_missing_skill_config_vars() -> List[Dict[str, Any]]` — Return skill-declared config vars that are missing or empty in config.yaml.
- `providers_dict_to_custom_providers(providers_dict: Any) -> List[Dict[str, Any]]` — Normalize ``providers`` config entries into the legacy custom-provider shape.
- _(+25 more functions)_

### `vector_cli/copilot_auth.py`

_GitHub Copilot authentication utilities._

**Functions:**

- `validate_copilot_token(token: str) -> tuple[bool, str]` — Validate that a token is usable with the Copilot API.
- `resolve_copilot_token() -> tuple[str, str]` — Resolve a GitHub token suitable for Copilot API use.
- `copilot_device_code_login(host: str, timeout_seconds: float) -> Optional[str]` — Run the GitHub OAuth device code flow for Copilot.
- `exchange_copilot_token(raw_token: str, timeout: float) -> tuple[str, float]` — Exchange a raw GitHub token for a short-lived Copilot API token.
- `get_copilot_api_token(raw_token: str) -> str` — Exchange a raw GitHub token for a Copilot API token, with fallback.
- `copilot_request_headers(is_agent_turn: bool, is_vision: bool) -> dict[str, str]` — Build the standard headers for Copilot API requests.

### `vector_cli/cron.py`

_Cron subcommand for vector CLI._

**Functions:**

- `cron_list(show_all: bool)` — List all scheduled jobs.
- `cron_tick()` — Run due jobs once and exit.
- `cron_status()` — Show cron execution status.
- `cron_create(args)`
- `cron_edit(args)`
- `cron_command(args)` — Handle cron subcommands.

### `vector_cli/curses_ui.py`

_Shared curses-based UI components for VectorCode CLI._

**Functions:**

- `flush_stdin() -> None` — Flush any stray bytes from the stdin input buffer.
- `curses_checklist(title: str, items: List[str], selected: Set[int], cancel_returns: Set[int] | None, status_fn: Optional[Callable[[Set[int]], str]]) -> Set[int]` — Curses multi-select checklist. Returns set of selected indices.
- `curses_radiolist(title: str, items: List[str], selected: int, cancel_returns: int | None, description: str | None) -> int` — Curses single-select radio list. Returns the selected index.
- `curses_single_select(title: str, items: List[str], default_index: int, cancel_label: str) -> int | None` — Curses single-select menu. Returns selected index or None on cancel.

### `vector_cli/debug.py`

_``vector debug`` — debug tools for VectorCode._

**Classes:**

- **`LogSnapshot`** — Single-read snapshot of a log file used by debug-share.

**Functions:**

- `delete_paste(url: str) -> bool` — Delete a paste from paste.rs.  Returns True on success.
- `upload_to_pastebin(content: str, expiry_days: int) -> str` — Upload *content* to a paste service, trying paste.rs then dpaste.com.
- `collect_debug_report(log_lines: int, dump_text: str, log_snapshots: Optional[dict[str, LogSnapshot]]) -> str` — Build the summary debug report: system dump + log tails.
- `run_debug_share(args)` — Collect debug report + full logs, upload each, print URLs.
- `run_debug_delete(args)` — Delete one or more paste URLs uploaded by /debug.
- `run_debug(args)` — Route debug subcommands.

### `vector_cli/default_soul.py`

_Default SOUL.md template seeded into VECTOR_HOME on first run._

### `vector_cli/dingtalk_auth.py`

_DingTalk Device Flow authorization._

**Classes:**

- **`RegistrationError`** — Raised when a DingTalk registration API call fails.

**Functions:**

- `begin_registration() -> dict` — Start a device-flow registration.
- `poll_registration(device_code: str) -> dict` — Poll the registration status once.
- `wait_for_registration_success(device_code: str, interval: int, expires_in: int, on_waiting: Optional[callable]) -> Tuple[str, str]` — Block until the registration succeeds or times out.
- `render_qr_to_terminal(url: str) -> bool` — Render *url* as a compact QR code in the terminal.
- `dingtalk_qr_auth() -> Optional[Tuple[str, str]]` — Run the interactive QR-code device-flow authorization.

### `vector_cli/doctor.py`

_Doctor command for vector CLI._

**Functions:**

- `check_ok(text: str, detail: str)`
- `check_warn(text: str, detail: str)`
- `check_fail(text: str, detail: str)`
- `check_info(text: str)`
- `run_doctor(args)` — Run diagnostic checks.

### `vector_cli/dump.py`

_Dump command for vector CLI._

**Functions:**

- `run_dump(args)` — Output a compact, copy-pasteable setup summary.

### `vector_cli/env_loader.py`

_Helpers for loading VectorCode .env files consistently across entrypoints._

**Functions:**

- `load_vector_dotenv(vector_home: str | os.PathLike | None, project_env: str | os.PathLike | None) -> list[Path]` — Load VectorCode environment files with user config taking precedence.

### `vector_cli/fallback_cmd.py`

_vector fallback — manage the fallback provider chain._

**Functions:**

- `cmd_fallback_list(args) -> None` — Print the current fallback chain.
- `cmd_fallback_add(args) -> None` — Launch the same picker as `vector model`, then append the selection to the chain.
- `cmd_fallback_remove(args) -> None` — Pick an entry from the chain and remove it.
- `cmd_fallback_clear(args) -> None` — Remove all fallback entries (with confirmation).
- `cmd_fallback(args) -> None` — Top-level dispatcher for ``vector fallback [subcommand]``.

### `vector_cli/gateway.py`

_Gateway subcommand for vector CLI._

**Classes:**

- **`GatewayRuntimeSnapshot`**
  - `running(self) -> bool`
  - `has_process_service_mismatch(self) -> bool`
- **`UserSystemdUnavailableError`** — Raised when ``systemctl --user`` cannot reach the user D-Bus session.

**Functions:**

- `find_gateway_pids(exclude_pids: set | None, all_profiles: bool) -> list` — Find PIDs of running gateway processes.
- `get_gateway_runtime_snapshot(system: bool) -> GatewayRuntimeSnapshot` — Return a unified view of gateway liveness for the current profile.
- `kill_gateway_processes(force: bool, exclude_pids: set | None, all_profiles: bool) -> int` — Kill any running gateway processes. Returns count killed.
- `stop_profile_gateway() -> bool` — Stop only the gateway for the current profile (VECTOR_HOME-scoped).
- `is_linux() -> bool`
- `supports_systemd_services() -> bool`
- `is_macos() -> bool`
- `is_windows() -> bool`
- `get_service_name() -> str` — Derive a systemd service name scoped to this VECTOR_HOME.
- `get_systemd_unit_path(system: bool) -> Path`
- `get_installed_systemd_scopes() -> list[str]`
- `has_conflicting_systemd_units() -> bool`
- `has_legacy_vector_units() -> bool` — Return True when any legacy VectorCode gateway unit files exist.
- `print_legacy_unit_warning() -> None` — Warn about legacy VectorCode gateway unit files if any are installed.
- `remove_legacy_vector_units(interactive: bool, dry_run: bool) -> tuple[int, list[Path]]` — Stop, disable, and remove legacy VectorCode gateway unit files.
- _(+29 more functions)_

### `vector_cli/hooks.py`

_vector hooks — inspect and manage shell-script hooks._

**Functions:**

- `hooks_command(args) -> None` — Entry point for ``vector hooks`` — dispatches to the requested action.

### `vector_cli/logs.py`

_``vector logs`` — view and filter VectorCode log files._

**Functions:**

- `tail_log(log_name: str, num_lines: int, follow: bool, level: Optional[str], session: Optional[str], since: Optional[str], component: Optional[str]) -> None` — Read and display log lines, optionally following in real time.
- `list_logs() -> None` — Print available log files with sizes.

### `vector_cli/main.py`

_VectorCode CLI - Main entry point._

**Functions:**

- `cmd_chat(args)` — Run interactive chat CLI.
- `cmd_gateway(args)` — Gateway management commands.
- `cmd_whatsapp(args)` — Set up WhatsApp: choose mode, configure, install bridge, pair via QR.
- `cmd_setup(args)` — Interactive setup wizard.
- `cmd_model(args)` — Select default model — starts with provider selection, then model picker.
- `select_provider_and_model(args)` — Core provider selection + model picking logic.
- `cmd_login(args)` — Authenticate VectorCode CLI with a provider.
- `cmd_logout(args)` — Clear provider authentication.
- `cmd_auth(args)` — Manage pooled credentials.
- `cmd_status(args)` — Show status of all components.
- `cmd_cron(args)` — Cron job management.
- `cmd_webhook(args)` — Webhook subscription management.
- `cmd_slack(args)` — Slack integration helpers.
- `cmd_hooks(args)` — Shell-hook inspection and management.
- `cmd_doctor(args)` — Check configuration and dependencies.
- _(+13 more functions)_

### `vector_cli/mcp_config.py`

_MCP Server Management CLI — ``vector mcp`` subcommand._

**Functions:**

- `cmd_mcp_add(args)` — Add a new MCP server with discovery-first tool selection.
- `cmd_mcp_remove(args)` — Remove an MCP server from config.
- `cmd_mcp_list(args)` — List all configured MCP servers.
- `cmd_mcp_test(args)` — Test connection to an MCP server.
- `cmd_mcp_login(args)` — Force re-authentication for an OAuth-based MCP server.
- `cmd_mcp_configure(args)` — Reconfigure which tools are enabled for an existing MCP server.
- `mcp_command(args)` — Main dispatcher for ``vector mcp`` subcommands.

### `vector_cli/memory_setup.py`

_vector memory setup|status — configure memory provider plugins._

**Functions:**

- `cmd_setup_provider(provider_name: str) -> None` — Run memory setup for a specific provider, skipping the picker.
- `cmd_setup(args) -> None` — Interactive memory provider setup wizard.
- `cmd_status(args) -> None` — Show current memory provider config.
- `memory_command(args) -> None` — Route memory subcommands.

### `vector_cli/model_catalog.py`

_Remote model catalog fetcher._

**Functions:**

- `get_catalog(force_refresh: bool) -> dict[str, Any]` — Return the parsed model catalog manifest, or an empty dict on failure.
- `get_curated_openrouter_models() -> list[tuple[str, str]] | None` — Return OpenRouter's curated ``[(id, description), ...]`` from the manifest.
- `get_curated_nous_models() -> list[str] | None` — Return Nous Portal's curated list of model ids from the manifest.
- `reset_cache() -> None` — Clear the in-process cache. Used by tests and ``vector model --refresh``.

### `vector_cli/model_normalize.py`

_Per-provider model name normalization._

**Functions:**

- `detect_vendor(model_name: str) -> Optional[str]` — Detect the vendor slug from a bare model name.
- `normalize_model_for_provider(model_input: str, target_provider: str) -> str` — Translate a model name into the format the target provider's API expects.

### `vector_cli/model_switch.py`

_Shared model-switching logic for CLI and gateway /model commands._

**Classes:**

- **`ModelIdentity`** — Vendor slug and family prefix used for catalog resolution.
- **`DirectAlias`** — Exact model mapping that bypasses catalog resolution.
- **`ModelSwitchResult`** — Result of a model switch attempt.
- **`CustomAutoResult`** — Result of switching to bare 'custom' provider with auto-detect.

**Functions:**

- `is_legacy_non_agentic(model_name: str) -> bool` — Return True if *model_name* is a real Nous VectorCode 3/4 chat model.
- `parse_model_flags(raw_args: str) -> tuple[str, str, bool]` — Parse --provider and --global flags from /model command args.
- `resolve_alias(raw_input: str, current_provider: str) -> Optional[tuple[str, str, str]]` — Resolve a short alias against the current provider's catalog.
- `get_authenticated_provider_slugs(current_provider: str, user_providers: dict, custom_providers: list | None) -> list[str]` — Return slugs of providers that have credentials.
- `resolve_display_context_length(model: str, provider: str, base_url: str, api_key: str, model_info: Optional[ModelInfo], custom_providers: list | None) -> Optional[int]` — Resolve the context length to show in /model output.
- `switch_model(raw_input: str, current_provider: str, current_model: str, current_base_url: str, current_api_key: str, is_global: bool, explicit_provider: str, user_providers: dict, custom_providers: list | None) -> ModelSwitchResult` — Core model-switching pipeline shared between CLI and gateway.
- `list_authenticated_providers(current_provider: str, current_base_url: str, user_providers: dict, custom_providers: list | None, max_models: int) -> List[dict]` — Detect which providers have credentials and list their curated models.

### `vector_cli/models.py`

_Canonical model catalogs and lightweight validation helpers._

**Classes:**

- **`ProviderEntry`**

**Functions:**

- `fetch_nous_account_tier(access_token: str, portal_base_url: str) -> dict[str, Any]` — Fetch the user's Nous Portal account/subscription info.
- `is_nous_free_tier(account_info: dict[str, Any]) -> bool` — Return True if the account info indicates a free (unpaid) tier.
- `partition_nous_models_by_tier(model_ids: list[str], pricing: dict[str, dict[str, str]], free_tier: bool) -> tuple[list[str], list[str]]` — Split Nous models into (selectable, unavailable) based on user tier.
- `check_nous_free_tier() -> bool` — Check if the current Nous Portal user is on a free (unpaid) tier.
- `fetch_nous_recommended_models(portal_base_url: str, timeout: float, force_refresh: bool) -> dict[str, Any]` — Fetch the Nous Portal's curated recommended-models payload.
- `get_nous_recommended_aux_model(vision: bool, free_tier: Optional[bool], portal_base_url: str, force_refresh: bool) -> Optional[str]` — Return the Portal's recommended model name for an auxiliary task.
- `get_default_model_for_provider(provider: str) -> str` — Return the default model for a provider, or empty string if unknown.
- `fetch_openrouter_models(timeout: float, force_refresh: bool) -> list[tuple[str, str]]` — Return the curated OpenRouter picker list, refreshed from the live catalog when possible.
- `model_ids(force_refresh: bool) -> list[str]` — Return just the OpenRouter model-id strings.
- `get_curated_nous_model_ids() -> list[str]` — Return the curated Nous Portal model-id list.
- `fetch_ai_gateway_models(timeout: float, force_refresh: bool) -> list[tuple[str, str]]` — Return the curated AI Gateway picker list, refreshed from the live catalog when possible.
- `ai_gateway_model_ids(force_refresh: bool) -> list[str]` — Return just the AI Gateway model-id strings.
- `format_model_pricing_table(models: list[tuple[str, str]], pricing_map: dict[str, dict[str, str]], current_model: str, indent: str) -> list[str]` — Build a column-aligned model+pricing table for terminal display.
- `fetch_models_with_pricing(api_key: str | None, base_url: str, timeout: float, force_refresh: bool) -> dict[str, dict[str, str]]` — Fetch ``/v1/models`` and return ``{model_id: {prompt, completion}}`` pricing.
- `fetch_ai_gateway_pricing(timeout: float, force_refresh: bool) -> dict[str, dict[str, str]]` — Fetch Vercel AI Gateway /v1/models and return vector-shaped pricing.
- _(+24 more functions)_

### `vector_cli/nous_subscription.py`

_Helpers for Nous subscription managed-tool capabilities._

**Classes:**

- **`NousFeatureState`**
- **`NousSubscriptionFeatures`**
  - `web(self) -> NousFeatureState`
  - `image_gen(self) -> NousFeatureState`
  - `tts(self) -> NousFeatureState`
  - `browser(self) -> NousFeatureState`
  - `modal(self) -> NousFeatureState`
  - `items(self) -> Iterable[NousFeatureState]`

**Functions:**

- `get_nous_subscription_features(config: Optional[Dict[str, object]]) -> NousSubscriptionFeatures`
- `apply_nous_managed_defaults(config: Dict[str, object], enabled_toolsets: Optional[Iterable[str]]) -> set[str]`
- `get_gateway_eligible_tools(config: Optional[Dict[str, object]]) -> tuple[list[str], list[str], list[str]]` — Return (unconfigured, has_direct, already_managed) tool key lists.
- `apply_gateway_defaults(config: Dict[str, object], tool_keys: list[str]) -> set[str]` — Apply Tool Gateway config for the given tool keys.
- `prompt_enable_tool_gateway(config: Dict[str, object]) -> set[str]` — If eligible tools exist, prompt the user to enable the Tool Gateway.

### `vector_cli/oneshot.py`

_Oneshot (-z) mode: send a prompt, get the final content block, exit._

**Functions:**

- `run_oneshot(prompt: str, model: Optional[str], provider: Optional[str]) -> int` — Execute a single prompt and print only the final content block.

### `vector_cli/pairing.py`

_CLI commands for the DM pairing system._

**Functions:**

- `pairing_command(args)` — Handle vector pairing subcommands.

### `vector_cli/platforms.py`

_Shared platform registry for VectorCode._

**Classes:**

- **`PlatformInfo`** — Metadata for a single platform entry.

**Functions:**

- `platform_label(key: str, default: str) -> str` — Return the display label for a platform key, or *default*.

### `vector_cli/plugins.py`

_VectorCode Plugin System_

**Classes:**

- **`PluginManifest`** — Parsed representation of a plugin.yaml manifest.
- **`LoadedPlugin`** — Runtime state for a single loaded plugin.
- **`PluginContext`** — Facade given to plugins so they can register tools and hooks.
  - `__init__(self, manifest: PluginManifest, manager: 'PluginManager')`
  - `register_tool(self, name: str, toolset: str, schema: dict, handler: Callable, check_fn: Callable | None, requires_env: list | None, is_async: bool, description: str, emoji: str) -> None`
  - `inject_message(self, content: str, role: str) -> bool`
  - `register_cli_command(self, name: str, help: str, setup_fn: Callable, handler_fn: Callable | None, description: str) -> None`
  - `register_command(self, name: str, handler: Callable, description: str, args_hint: str) -> None`
  - `dispatch_tool(self, tool_name: str, args: dict) -> str`
  - `register_context_engine(self, engine) -> None`
  - `register_image_gen_provider(self, provider) -> None`
  - _(+2 more methods)_
- **`PluginManager`** — Central manager that discovers, loads, and invokes plugins.
  - `__init__(self) -> None`
  - `discover_and_load(self, force: bool) -> None`
  - `invoke_hook(self, hook_name: str) -> List[Any]`
  - `list_plugins(self) -> List[Dict[str, Any]]`
  - `find_plugin_skill(self, qualified_name: str) -> Optional[Path]`
  - `list_plugin_skills(self, plugin_name: str) -> List[str]`
  - `remove_plugin_skill(self, qualified_name: str) -> None`

**Functions:**

- `get_plugin_manager() -> PluginManager` — Return (and lazily create) the global PluginManager singleton.
- `discover_plugins(force: bool) -> None` — Discover and load all plugins.
- `invoke_hook(hook_name: str) -> List[Any]` — Invoke a lifecycle hook on all loaded plugins.
- `get_pre_tool_call_block_message(tool_name: str, args: Optional[Dict[str, Any]], task_id: str, session_id: str, tool_call_id: str) -> Optional[str]` — Check ``pre_tool_call`` hooks for a blocking directive.
- `get_plugin_context_engine()` — Return the plugin-registered context engine, or None.
- `get_plugin_command_handler(name: str) -> Optional[Callable]` — Return the handler for a plugin-registered slash command, or ``None``.
- `get_plugin_commands() -> Dict[str, dict]` — Return the full plugin commands dict (name → {handler, description, plugin}).
- `get_plugin_toolsets() -> List[tuple]` — Return plugin toolsets as ``(key, label, description)`` tuples.

### `vector_cli/plugins_cmd.py`

_``vector plugins`` CLI subcommand — install, update, remove, and list plugins._

**Functions:**

- `cmd_install(identifier: str, force: bool, enable: Optional[bool]) -> None` — Install a plugin from a Git URL or owner/repo shorthand.
- `cmd_update(name: str) -> None` — Update an installed plugin by pulling latest from its git remote.
- `cmd_remove(name: str) -> None` — Remove an installed plugin by name.
- `cmd_enable(name: str) -> None` — Add a plugin to the enabled allow-list (and remove it from disabled).
- `cmd_disable(name: str) -> None` — Remove a plugin from the enabled allow-list (and add to disabled).
- `cmd_list() -> None` — List all plugins (bundled + user) with enabled/disabled state.
- `cmd_toggle() -> None` — Interactive composite UI — general plugins + provider plugin categories.
- `plugins_command(args) -> None` — Dispatch vector plugins subcommands.

### `vector_cli/profiles.py`

_Profile management for multiple isolated VectorCode instances._

**Classes:**

- **`ProfileInfo`** — Summary information about a profile.

**Functions:**

- `validate_profile_name(name: str) -> None` — Raise ``ValueError`` if *name* is not a valid profile identifier.
- `get_profile_dir(name: str) -> Path` — Resolve a profile name to its VECTOR_HOME directory.
- `profile_exists(name: str) -> bool` — Check whether a profile directory exists.
- `check_alias_collision(name: str) -> Optional[str]` — Return a human-readable collision message, or None if the name is safe.
- `create_wrapper_script(name: str) -> Optional[Path]` — Create a shell wrapper script at ~/.local/bin/<name>.
- `remove_wrapper_script(name: str) -> bool` — Remove the wrapper script for a profile. Returns True if removed.
- `list_profiles() -> List[ProfileInfo]` — Return info for all profiles, including the default.
- `create_profile(name: str, clone_from: Optional[str], clone_all: bool, clone_config: bool, no_alias: bool) -> Path` — Create a new profile directory.
- `seed_profile_skills(profile_dir: Path, quiet: bool) -> Optional[dict]` — Seed bundled skills into a profile via subprocess.
- `delete_profile(name: str, yes: bool) -> Path` — Delete a profile, its wrapper script, and its gateway service.
- `get_active_profile() -> str` — Read the sticky active profile name.
- `set_active_profile(name: str) -> None` — Set the sticky active profile.
- `get_active_profile_name() -> str` — Infer the current profile name from VECTOR_HOME.
- `export_profile(name: str, output_path: str) -> Path` — Export a profile to a tar.gz archive.
- `import_profile(archive_path: str, name: Optional[str]) -> Path` — Import a profile from a tar.gz archive.
- _(+4 more functions)_

### `vector_cli/providers.py`

_Single source of truth for provider identity in VectorCode._

**Classes:**

- **`VectorCodeOverlay`** — VectorCode-specific provider metadata layered on top of models.dev.
- **`ProviderDef`** — Complete provider definition — merged from all sources.

**Functions:**

- `normalize_provider(name: str) -> str` — Resolve aliases and normalise casing to a canonical provider id.
- `get_provider(name: str) -> Optional[ProviderDef]` — Look up a built-in provider by id or alias.
- `get_label(provider_id: str) -> str` — Get a human-readable display name for a provider.
- `is_aggregator(provider: str) -> bool` — Return True when the provider is a multi-model aggregator.
- `determine_api_mode(provider: str, base_url: str) -> str` — Determine the API mode (wire protocol) for a provider/endpoint.
- `resolve_user_provider(name: str, user_config: Dict[str, Any]) -> Optional[ProviderDef]` — Resolve a provider from the user's config.yaml ``providers:`` section.
- `custom_provider_slug(display_name: str) -> str` — Build a canonical slug for a custom_providers entry.
- `resolve_custom_provider(name: str, custom_providers: Optional[List[Dict[str, Any]]]) -> Optional[ProviderDef]` — Resolve a provider from the user's config.yaml ``custom_providers`` list.
- `resolve_provider_full(name: str, user_providers: Optional[Dict[str, Any]], custom_providers: Optional[List[Dict[str, Any]]]) -> Optional[ProviderDef]` — Full resolution chain: built-in → models.dev → user config.

### `vector_cli/pty_bridge.py`

_PTY bridge for `vector dashboard` chat tab._

**Classes:**

- **`PtyUnavailableError`** — Raised when a PTY cannot be created on this platform.
- **`PtyBridge`** — Thin wrapper around ``ptyprocess.PtyProcess`` for byte streaming.
  - `__init__(self, proc: 'ptyprocess.PtyProcess')`
  - `is_available(cls) -> bool`
  - `spawn(cls, argv: Sequence[str], cwd: Optional[str], env: Optional[dict], cols: int, rows: int) -> 'PtyBridge'`
  - `pid(self) -> int`
  - `is_alive(self) -> bool`
  - `read(self, timeout: float) -> Optional[bytes]`
  - `write(self, data: bytes) -> None`
  - `resize(self, cols: int, rows: int) -> None`
  - _(+1 more methods)_

### `vector_cli/runtime_provider.py`

_Shared runtime provider resolution for CLI, gateway, cron, and helpers._

**Functions:**

- `resolve_requested_provider(requested: Optional[str]) -> str` — Resolve provider request from explicit arg, config, then env.
- `resolve_runtime_provider(requested: Optional[str], explicit_api_key: Optional[str], explicit_base_url: Optional[str], target_model: Optional[str]) -> Dict[str, Any]` — Resolve runtime provider credentials for agent execution.
- `format_runtime_provider_error(error: Exception) -> str`

### `vector_cli/setup.py`

_Interactive setup wizard for VectorCode._

**Functions:**

- `print_header(title: str)` — Print a section header.
- `is_interactive_stdin() -> bool` — Return True when stdin looks like a usable interactive TTY.
- `print_noninteractive_setup_guidance(reason: str | None) -> None` — Print guidance for headless/non-interactive setup flows.
- `prompt(question: str, default: str, password: bool) -> str` — Prompt for input with optional default.
- `prompt_choice(question: str, choices: list, default: int, description: str | None) -> int` — Prompt for a choice from a list with arrow key navigation.
- `prompt_yes_no(question: str, default: bool) -> bool` — Prompt for yes/no. Ctrl+C exits, empty input returns default.
- `prompt_checklist(title: str, items: list, pre_selected: list) -> list` — Display a multi-select checklist and return the indices of selected items.
- `setup_model_provider(config: dict, quick: bool)` — Configure the inference provider and default model.
- `setup_tts(config: dict)` — Standalone TTS setup (for 'vector setup tts').
- `setup_terminal_backend(config: dict)` — Configure the terminal execution backend.
- `setup_agent_settings(config: dict)` — Configure agent behavior: iterations, progress display, compression, session reset.
- `setup_gateway(config: dict)` — Configure messaging platform integrations.
- `setup_tools(config: dict, first_install: bool)` — Configure tools — delegates to the unified tools_command() in tools_config.py.
- `run_setup_wizard(args)` — Run the interactive setup wizard.

### `vector_cli/skills_config.py`

_Skills configuration for VectorCode._

**Functions:**

- `get_disabled_skills(config: dict, platform: Optional[str]) -> Set[str]` — Return disabled skill names. Platform-specific list falls back to global.
- `save_disabled_skills(config: dict, disabled: Set[str], platform: Optional[str])` — Persist disabled skill names to config.
- `skills_command(args)` — Entry point for `vector skills`.

### `vector_cli/skills_hub.py`

_Skills Hub CLI — Unified interface for the VectorCode Skills Hub._

**Functions:**

- `do_search(query: str, source: str, limit: int, console: Optional[Console]) -> None` — Search registries and display results as a Rich table.
- `do_browse(page: int, page_size: int, source: str, console: Optional[Console]) -> None` — Browse all available skills across registries, paginated.
- `do_install(identifier: str, category: str, force: bool, console: Optional[Console], skip_confirm: bool, invalidate_cache: bool, name_override: str) -> None` — Fetch, quarantine, scan, confirm, and install a skill.
- `do_inspect(identifier: str, console: Optional[Console]) -> None` — Preview a skill's SKILL.md content without installing.
- `browse_skills(page: int, page_size: int, source: str) -> dict` — Paginated hub browse for programmatic callers (e.g. TUI gateway).
- `inspect_skill(identifier: str) -> Optional[dict]` — Skill metadata (+ SKILL.md preview) for programmatic callers.
- `do_list(source_filter: str, enabled_only: bool, console: Optional[Console]) -> None` — List installed skills, distinguishing hub, builtin, and local skills.
- `do_check(name: Optional[str], console: Optional[Console]) -> None` — Check hub-installed skills for upstream updates.
- `do_update(name: Optional[str], console: Optional[Console]) -> None` — Update hub-installed skills with upstream changes.
- `do_audit(name: Optional[str], console: Optional[Console]) -> None` — Re-run security scan on installed hub skills.
- `do_uninstall(name: str, console: Optional[Console], skip_confirm: bool, invalidate_cache: bool) -> None` — Remove a hub-installed skill with confirmation.
- `do_reset(name: str, restore: bool, console: Optional[Console], skip_confirm: bool, invalidate_cache: bool) -> None` — Reset a bundled skill's manifest tracking (+ optionally restore from bundled).
- `do_tap(action: str, repo: str, console: Optional[Console]) -> None` — Manage taps (custom GitHub repo sources).
- `do_publish(skill_path: str, target: str, repo: str, console: Optional[Console]) -> None` — Publish a local skill to a registry (GitHub PR or ClawHub submission).
- `do_snapshot_export(output_path: str, console: Optional[Console]) -> None` — Export current hub skill configuration to a portable JSON file.
- _(+3 more functions)_

### `vector_cli/skin_engine.py`

_VectorCode CLI skin/theme engine._

**Classes:**

- **`SkinConfig`** — Complete skin configuration.
  - `get_color(self, key: str, fallback: str) -> str`
  - `get_spinner_wings(self) -> List[Tuple[str, str]]`
  - `get_branding(self, key: str, fallback: str) -> str`

**Functions:**

- `list_skins() -> List[Dict[str, str]]` — List all available skins (built-in + user-installed).
- `load_skin(name: str) -> SkinConfig` — Load a skin by name. Checks user skins first, then built-in.
- `get_active_skin() -> SkinConfig` — Get the currently active skin config (cached).
- `set_active_skin(name: str) -> SkinConfig` — Switch the active skin. Returns the new SkinConfig.
- `get_active_skin_name() -> str` — Get the name of the currently active skin.
- `init_skin_from_config(config: dict) -> None` — Initialize the active skin from CLI config at startup.
- `get_active_prompt_symbol(fallback: str) -> str` — Get the interactive prompt symbol from the active skin.
- `get_active_help_header(fallback: str) -> str` — Get the /help header from the active skin.
- `get_active_goodbye(fallback: str) -> str` — Get the goodbye line from the active skin.
- `get_prompt_toolkit_style_overrides() -> Dict[str, str]` — Return prompt_toolkit style overrides derived from the active skin.

### `vector_cli/slack_cli.py`

_``vector slack ...`` CLI subcommands._

**Functions:**

- `slack_manifest_command(args) -> int` — Print or write a Slack app manifest JSON.

### `vector_cli/status.py`

_Status command for vector CLI._

**Functions:**

- `check_mark(ok: bool) -> str`
- `redact_key(key: str) -> str` — Redact an API key for display.
- `show_status(args)` — Show status of all VectorCode components.

### `vector_cli/timeouts.py`

**Functions:**

- `get_provider_request_timeout(provider_id: str, model: str | None) -> float | None` — Return a configured provider request timeout in seconds, if any.
- `get_provider_stale_timeout(provider_id: str, model: str | None) -> float | None` — Return a configured non-stream stale timeout in seconds, if any.

### `vector_cli/tips.py`

_Random tips shown at CLI session start to help users discover features._

**Functions:**

- `get_random_tip(exclude_recent: int) -> str` — Return a random tip string.

### `vector_cli/tools_config.py`

_Unified tool configuration for VectorCode._

**Functions:**

- `tools_command(args, first_install: bool, config: dict)` — Entry point for `vector tools` and `vector setup tools`.
- `tools_disable_enable_command(args)` — Enable, disable, or list tools for a platform.

### `vector_cli/uninstall.py`

_VectorCode Uninstaller._

**Functions:**

- `log_info(msg: str)`
- `log_success(msg: str)`
- `log_warn(msg: str)`
- `get_project_root() -> Path` — Get the project installation directory.
- `find_shell_configs() -> list` — Find shell configuration files that might have PATH entries.
- `remove_path_from_shell_configs()` — Remove VectorCode PATH entries from shell configuration files.
- `remove_wrapper_script()` — Remove the vector wrapper script if it exists.
- `uninstall_gateway_service()` — Stop and uninstall the gateway service (systemd, launchd) and kill any
- `run_uninstall(args)` — Run the uninstall process.

### `vector_cli/voice.py`

_Process-wide voice recording + TTS API for the TUI gateway._

**Functions:**

- `start_recording() -> None` — Begin capturing from the default input device (push-to-talk).
- `stop_and_transcribe() -> Optional[str]` — Stop the active push-to-talk recording, transcribe, return text.
- `start_continuous(on_transcript: Callable[[str], None], on_status: Optional[Callable[[str], None]], on_silent_limit: Optional[Callable[[], None]], silence_threshold: int, silence_duration: float) -> None` — Start a VAD-driven continuous recording loop.
- `stop_continuous() -> None` — Stop the active continuous loop and release the microphone.
- `is_continuous_active() -> bool` — Whether a continuous voice loop is currently running.
- `speak_text(text: str) -> None` — Synthesize ``text`` with the configured TTS provider and play it.

### `vector_cli/web_server.py`

_VectorCode — Web UI server._

**Classes:**

- **`ConfigUpdate`**
- **`EnvVarUpdate`**
- **`EnvVarDelete`**
- **`EnvVarReveal`**
- **`OAuthSubmitBody`**
- **`CronJobCreate`**
- **`CronJobUpdate`**
- **`SkillToggle`**
- **`RawConfigUpdate`**
- **`ThemeSetBody`**

**Functions:**

- `host_header_middleware(request: Request, call_next)` — Reject requests whose Host header doesn't match the bound interface.
- `auth_middleware(request: Request, call_next)` — Require the session token on all /api/ routes except the public list.
- `get_status()`
- `restart_gateway()` — Kick off a ``vector gateway restart`` in the background.
- `update_vector()` — Kick off ``vector update`` in the background.
- `get_action_status(name: str, lines: int)` — Tail an action log and report whether the process is still running.
- `get_sessions(limit: int, offset: int)`
- `search_sessions(q: str, limit: int)` — Full-text search across session message content using FTS5.
- `get_config()`
- `get_defaults()`
- `get_schema()`
- `get_model_info()` — Return resolved model metadata for the currently configured model.
- `update_config(body: ConfigUpdate)`
- `get_env_vars()`
- `set_env_var(body: EnvVarUpdate)`
- _(+37 more functions)_

### `vector_cli/webhook.py`

_vector webhook — manage dynamic webhook subscriptions from the CLI._

**Functions:**

- `webhook_command(args)` — Entry point for 'vector webhook' subcommand.


---

## (root)

### `vector_constants.py`

_VectorCode home directory constants — VectorCode implementation._

**Functions:**

- `get_vector_home() -> Path` — Return the VectorCode home directory.
- `get_vector_skills_dir() -> Path` — Return the user skills directory: ~/.vector/skills (or $VECTOR_HOME/skills).
- `get_vector_sessions_dir() -> Path` — Return the sessions directory: ~/.vector/sessions.
- `get_vector_memory_path() -> Path` — Return the persistent memory file path: ~/.vector/memory.md.
- `get_vector_config_path() -> Path` — Return the global config file path: ~/.config/vector/config.toml.
- `display_vector_home() -> str` — Return a human-friendly string for the VectorCode home directory.
- `get_vector_data_dir() -> Path` — Return the data subdirectory: ~/.vector/data.
- `get_vector_logs_dir() -> Path` — Return the logs subdirectory: ~/.vector/logs.
- `get_config_path() -> Path` — Alias for get_vector_config_path — back-compat for legacy imports.
- `get_subprocess_home() -> Path` — Return the home directory for subprocess execution.
- `get_log_dir() -> Path` — Return the logs directory: ~/.vector/logs.
- `get_skills_hub_dir() -> Path` — Return the skills hub cache directory.
- `display_home() -> str` — Alias for display_vector_home.


---

## (root)

### `vector_logging.py`

_Centralized logging setup for VectorCode._

**Functions:**

- `set_session_context(session_id: str) -> None` — Set the session ID for the current thread.
- `clear_session_context() -> None` — Clear the session ID for the current thread.
- `setup_logging(vector_home: Optional[Path], log_level: Optional[str], max_size_mb: Optional[int], backup_count: Optional[int], mode: Optional[str], force: bool) -> Path` — Configure the VectorCode logging subsystem.
- `setup_verbose_logging() -> None` — Enable DEBUG-level console logging for ``--verbose`` / ``-v`` mode.


---

## (root)

### `vector_state.py`

_SQLite State Store for VectorCode._

**Classes:**

- **`SessionDB`** — SQLite-backed session storage with FTS5 search.
  - `__init__(self, db_path: Path)`
  - `close(self)`
  - `create_session(self, session_id: str, source: str, model: str, model_config: Dict[str, Any], system_prompt: str, user_id: str, parent_session_id: str) -> str`
  - `end_session(self, session_id: str, end_reason: str) -> None`
  - `reopen_session(self, session_id: str) -> None`
  - `update_system_prompt(self, session_id: str, system_prompt: str) -> None`
  - `update_token_counts(self, session_id: str, input_tokens: int, output_tokens: int, model: str, cache_read_tokens: int, cache_write_tokens: int, reasoning_tokens: int, estimated_cost_usd: Optional[float], actual_cost_usd: Optional[float], cost_status: Optional[str], cost_source: Optional[str], pricing_version: Optional[str], billing_provider: Optional[str], billing_base_url: Optional[str], billing_mode: Optional[str], api_call_count: int, absolute: bool) -> None`
  - `ensure_session(self, session_id: str, source: str, model: str) -> None`
  - _(+27 more methods)_


---

## (root)

### `vector_time.py`

_Timezone-aware clock for VectorCode._

**Functions:**

- `get_timezone() -> Optional[ZoneInfo]` — Return the user's configured ZoneInfo, or None (meaning server-local).
- `now() -> datetime` — Return the current time as a timezone-aware datetime.

