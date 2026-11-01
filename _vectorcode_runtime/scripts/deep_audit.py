"""
Deep audit of vectorcode/src — broken imports, undefined references,
wrong logic, missing return values, and wiring gaps.
"""
from __future__ import annotations
from loguru import logger
import ast
import sys
from pathlib import Path
from collections import defaultdict

vectorcode_root = Path(__file__).parent.parent / "vectorcode"
vc = vectorcode_root / "src"
py_files = sorted(f for f in vc.rglob("*.py") if "__pycache__" not in str(f))

print(f"Deep-auditing {len(py_files)} files...", flush=True)

# ── 1. Collect every name defined anywhere in vectorcode ─────────────────
defined_names: set[str] = set()
module_map: dict[str, Path] = {}   # stem -> path

for py in py_files:
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        continue
    stem = py.stem
    defined_names.add(stem)
    module_map[stem] = py
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined_names.add(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                defined_names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                defined_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined_names.add(alias.asname or alias.name)

BUILTINS = frozenset(dir(__builtins__) if isinstance(__builtins__, dict)
                     else dir(__builtins__))
SKIP_NAMES = BUILTINS | {
    "self", "cls", "args", "kwargs", "T", "K", "V", "R", "S", "E",
    "Protocol", "TypeVar", "Generic", "overload", "dataclass", "field",
    "Any", "Optional", "Union", "List", "Dict", "Set", "Tuple", "Callable",
    "Type", "ClassVar", "Final", "Literal", "TypedDict", "NamedTuple",
    "Iterator", "Generator", "AsyncIterator", "AsyncGenerator",
    "Awaitable", "Coroutine", "ContextManager", "AsyncContextManager",
    "NotImplementedError", "NotImplemented", "Ellipsis",
    "_", "__", "n", "i", "j", "k", "x", "y", "z", "e",
    "a", "b", "c", "d", "f", "g", "h", "m", "p", "q", "r", "s", "t",
    "u", "v", "w", "ok", "err", "__file__", "__builtins__",
}

# ── 2. Per-file checks ────────────────────────────────────────────────────
issues: list[tuple[str, str, int, str]] = []  # (level, rel_path, lineno, msg)
ENCLOSING_SCOPE_NAMES: dict[int, set[str]] = {}

IGNORE_IMPORTS = frozenset({
    # Third-party that may or may not be installed
    "anthropic", "openai", "httpx", "requests", "fastapi", "uvicorn",
    "pydantic", "loguru", "numpy", "torch", "transformers", "chromadb",
    "lightrag", "supabase", "watchdog", "pyautogui", "cv2", "mediapipe",
    "whisper", "sounddevice", "openwakeword", "yt_dlp", "instagrapi",
    "github", "google", "telegram", "discord", "slack", "twilio",
    "pushover", "mem0ai", "fastmcp", "rich", "click",
    "typer", "aiofiles", "aiohttp", "websockets", "cryptography", "jwt",
    "PIL", "matplotlib", "pandas", "scipy", "sklearn", "lightgbm",
    "optuna", "wandb", "mlflow", "dspy", "lancedb", "faiss", "annoy",
    "playwright", "selenium", "bs4", "lxml", "tweepy", "mastodon",
    "praw", "vkbottle", "telethon", "aiogram", "pyrogram",
    "mattermost_driver", "zulip", "irc", "xmpp", "slixmpp",
    "stripe", "braintree", "plaid", "web3", "eth_account", "solana",
    "boto3", "botocore", "azure", "firebase_admin",
    "docker", "kubernetes", "paramiko", "psutil", "GPUtil", "pynvml",
    "yaml", "toml", "dotenv", "msgpack", "protobuf", "grpc",
    "zmq", "nats", "redis", "celery", "dramatiq",
    "motor", "pymongo", "elasticsearch", "influxdb", "prometheus_client",
    "opentelemetry", "sentry_sdk", "datadog",
    "jinja2", "prompt_toolkit", "questionary", "arrow", "pendulum",
    "dateutil", "pytz", "humanize", "fuzzywuzzy", "rapidfuzz",
    "nltk", "spacy", "gensim", "tiktoken", "tokenizers",
    "networkx", "shapely", "pyproj", "geopy", "plotly", "streamlit",
    "gradio", "dash", "ipython", "dask", "ray", "polars", "pyarrow",
    "psycopg2", "asyncpg", "aiomysql", "aiosqlite", "pymysql",
    "orjson", "ujson", "marshmallow", "cerberus", "cattrs", "dacite",
    "attrs", "beartype", "typeguard", "typing_extensions",
    "anyio", "trio", "twisted", "tornado", "gevent",
    "magic", "chardet", "Crypto", "nacl", "argon2", "passlib", "bcrypt",
    "sqlcipher3", "langchain", "langgraph", "openai_agents",
    "anthropic_bedrock", "google_generativeai", "cohere",
    "mistralai", "together", "groq", "replicate", "huggingface_hub",
    "sentence_transformers", "datasets", "evaluate", "accelerate",
    "peft", "bitsandbytes", "unsloth", "trl", "einops",
    "aiosmtplib", "exchangelib", "caldav", "vobject",
    "gspread", "openpyxl", "xlsxwriter", "reportlab",
    "flask", "bottle", "falcon", "sanic", "blacksheep",
    "starlette", "litestar", "robyn", "hypercorn",
    "pynput", "keyboard", "mouse", "pygetwindow", "pywinauto",
    "win32api", "win32con", "winreg", "comtypes",
    "Xlib", "ewmh", "wnck", "AppKit", "Quartz", "pynput",
    "irc", "irctypes", "jaraco",
    "usearch", "qdrant_client", "weaviate", "pinecone",
    "tqdm", "alive_progress", "halo", "yaspin",
    "tabulate", "texttable", "terminaltables", "prettytable",
    "colorama", "termcolor", "blessed", "urwid", "curtsies",
    "appdirs", "platformdirs", "xdg", "click_spinner",
    "jsonlines", "ndjson", "bigjson",
    "pyperclip", "xerox", "clipboard",
    "pyttsx3", "kokoro", "edge_tts", "gtts",
    "deepgram", "assemblyai", "speechrecognition",
    "llama_cpp", "ctransformers", "gguf", "mlx", "coremltools",
    "onnx", "onnxruntime", "tensorrt", "triton",
    "airllm", "exllamav2", "awq", "gptq", "auto_gptq",
    "vllm", "text_generation", "lmdeploy",
    "outlines", "guidance_ai", "lmql",
    "semantic_kernel", "autogen", "crewai", "agentops",
    "langfuse", "langsmith", "arize", "whylogs",
    "litellm", "openrouter", "together_ai",
    "pymupdf", "pypdf", "pdfminer", "docx2txt", "python_docx",
    "pytesseract", "easyocr", "paddleocr", "surya",
    "yt_dlp", "ffmpeg", "moviepy", "imageio", "av",
    "soundfile", "librosa", "pyaudio", "pydub",
    "mss", "pyscreenshot", "scrot",
    "adb", "pure_python_adb", "uiautomator2",
    "frida", "angr", "capstone",
    "scapy", "pyshark", "dpkt",
    "nmap", "shodan", "censys",
    "metasploit", "impacket",
    "web3", "brownie", "ape", "hardhat",
    "solana", "anchorpy", "borsh_construct",
    "hyperliquid", "ccxt", "alpaca_trade_api",
    "yfinance", "pandas_datareader", "quandl",
    "backtrader", "zipline", "vectorbt",
    "stripe", "braintree", "paypalrestsdk",
    "twilio", "vonage", "messagebird", "infobip",
    "sendgrid", "mailchimp_transactional", "postmark",
    "resend", "loops", "klaviyo",
    "segment", "mixpanel", "amplitude", "posthog",
    "intercom", "zendesk", "freshdesk", "hubspot", "salesforce",
    "notion_client", "airtable", "coda", "clickup",
    "linear", "shortcut", "jira", "confluence",
    "vercel", "netlify", "railway", "fly",
    "github", "gitlab", "bitbucket",
    "terraform", "pulumi", "aws_cdk", "constructs",
})

def add_target_names(target: ast.AST, scope: set[str]) -> None:
    """Add names bound by assignment-like targets, including destructuring."""
    if isinstance(target, ast.Name):
        scope.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            add_target_names(elt, scope)
    elif isinstance(target, ast.Starred):
        add_target_names(target.value, scope)


def get_local_scope(tree: ast.Module, func_node) -> set[str]:
    """Get names visible in a function's scope."""
    scope: set[str] = set()
    # Module-level names
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                add_target_names(t, scope)
        elif isinstance(node, ast.AnnAssign):
            add_target_names(node.target, scope)
        elif isinstance(node, ast.Import):
            for a in node.names:
                scope.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                scope.add(a.asname or a.name)
    # Function args
    args = func_node.args
    for a in args.args + args.posonlyargs + args.kwonlyargs:
        scope.add(a.arg)
    if args.vararg:
        scope.add(args.vararg.arg)
    if args.kwarg:
        scope.add(args.kwarg.arg)
    scope |= ENCLOSING_SCOPE_NAMES.get(id(func_node), set())
    # Assigned within function
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                add_target_names(t, scope)
        elif isinstance(node, ast.AnnAssign):
            add_target_names(node.target, scope)
        elif isinstance(node, ast.AugAssign):
            add_target_names(node.target, scope)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            add_target_names(node.target, scope)
        elif isinstance(node, ast.NamedExpr):
            add_target_names(node.target, scope)
        elif isinstance(node, ast.Import):
            for a in node.names:
                scope.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                scope.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope.add(node.name)
        elif isinstance(node, ast.Global):
            for n in node.names:
                scope.add(n)
        elif isinstance(node, ast.Nonlocal):
            for n in node.names:
                scope.add(n)
        elif isinstance(node, ast.ListComp, ):
            for gen in node.generators:
                add_target_names(gen.target, scope)
        elif isinstance(node, (ast.DictComp, ast.SetComp, ast.GeneratorExp)):
            for gen in node.generators:
                add_target_names(gen.target, scope)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    add_target_names(item.optional_vars, scope)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                scope.add(node.name)
    return scope


def check_import_from(node: ast.ImportFrom, py: Path, rel: str) -> None:
    """Check if 'from X import Y' makes sense."""
    if node.module is None:
        return
    mod = node.module
    # Only check intra-vectorcode imports
    if not mod.startswith("vectorcode"):
        return
    # Convert module path to file path
    if mod.startswith("vectorcode.src."):
        parts = mod.replace("vectorcode.src.", "").split(".")
        candidate = vc.joinpath(*parts)
    else:
        parts = mod.replace("vectorcode.", "").split(".")
        candidate = vectorcode_root.joinpath(*parts)
    # Try as module file or package
    file_candidates = [
        candidate.with_suffix(".py"),
        candidate / "__init__.py",
    ]
    found = any(c.exists() for c in file_candidates)
    if not found:
        issues.append(("IMPORT", rel, node.lineno,
                       f"from {mod!r} import ... — module not found in vectorcode"))
    else:
        # Check that the imported names exist in the module
        target_file = next(c for c in file_candidates if c.exists())
        try:
            target_tree = ast.parse(target_file.read_text(encoding="utf-8", errors="replace"))
            target_names: set[str] = set()
            if target_file.name == "__init__.py":
                for child in target_file.parent.glob("*.py"):
                    if child.name != "__init__.py":
                        target_names.add(child.stem)
            for n in ast.walk(target_tree):
                if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    target_names.add(n.name)
                elif isinstance(n, ast.Assign):
                    for t in n.targets:
                        add_target_names(t, target_names)
                elif isinstance(n, ast.AnnAssign):
                    add_target_names(n.target, target_names)
                elif isinstance(n, ast.ImportFrom):
                    for a in n.names:
                        target_names.add(a.asname or a.name)
            for alias in node.names:
                name = alias.name
                if name != "*" and "*" not in target_names and name not in target_names:
                    issues.append(("IMPORT", rel, node.lineno,
                                   f"from {mod!r} import {name!r} — {name!r} not defined in {target_file.name}"))
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)


def iter_function_load_names(func_node):
    """Yield loaded Name nodes in a function, excluding nested scopes."""
    class _LoadNameVisitor(ast.NodeVisitor):
        def __init__(self):
            self.names = []

        def visit_FunctionDef(self, node):
            if node is func_node:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            if node is func_node:
                self.generic_visit(node)

        def visit_Lambda(self, node):
            return

        def visit_ClassDef(self, node):
            return

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                self.names.append(node)

    visitor = _LoadNameVisitor()
    visitor.visit(func_node)
    return visitor.names


def function_bindings(func_node) -> set[str]:
    bindings: set[str] = set()
    args = func_node.args
    for a in args.args + args.posonlyargs + args.kwonlyargs:
        bindings.add(a.arg)
    if args.vararg:
        bindings.add(args.vararg.arg)
    if args.kwarg:
        bindings.add(args.kwarg.arg)
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                add_target_names(t, bindings)
        elif isinstance(node, ast.AnnAssign):
            add_target_names(node.target, bindings)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            add_target_names(node.target, bindings)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    add_target_names(item.optional_vars, bindings)
    return bindings


class EnclosingScopeVisitor(ast.NodeVisitor):
    def __init__(self):
        self.stack: list[set[str]] = []

    def visit_FunctionDef(self, node):
        ENCLOSING_SCOPE_NAMES[id(node)] = set().union(*self.stack) if self.stack else set()
        self.stack.append(function_bindings(node))
        for stmt in node.body:
            self.visit(stmt)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        for stmt in node.body:
            self.visit(stmt)


for py in py_files:
    rel = str(py.relative_to(vc))
    try:
        text = py.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except SyntaxError as e:
        issues.append(("SYNTAX", rel, e.lineno or 0, str(e)[:100]))
        continue

    lines = text.splitlines()
    ENCLOSING_SCOPE_NAMES.clear()
    EnclosingScopeVisitor().visit(tree)

    # ── Check all from X import Y ──────────────────────────────────────
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            check_import_from(node, py, rel)

    # ── Check functions that reference undefined names ──────────────────
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local_scope = get_local_scope(tree, node)
        visible = local_scope | defined_names | SKIP_NAMES

        for child in iter_function_load_names(node):
            name = child.id
            if name in visible:
                continue
            lineno = getattr(child, "lineno", 0)
            if lineno and lineno <= len(lines):
                line_text = lines[lineno - 1].strip()
                # Skip names that look like they're from TYPE_CHECKING
                if "TYPE_CHECKING" in text and name[0].isupper():
                    continue
                # Skip comprehension variables
                if len(name) <= 2:
                    continue
                issues.append(("UNDEF", rel, lineno,
                               f"Name {name!r} used but not defined — line: {line_text[:60]}"))

    # ── Check for functions with missing return in non-None paths ─────
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorator_names = {
            getattr(dec, "id", getattr(dec, "attr", ""))
            for dec in node.decorator_list
        }
        if "abstractmethod" in decorator_names:
            continue
        # Skip if return annotation is None/nothing
        if isinstance(node.returns, ast.Constant) and node.returns.value is None:
            continue
        if node.returns is None:
            continue
        ann = ast.unparse(node.returns) if hasattr(ast, "unparse") else ""
        if ann in ("None", "NoReturn", "never"):
            continue
        # Check if any path has no return
        body = node.body
        last = body[-1] if body else None
        if isinstance(last, ast.Expr) and isinstance(last.value, ast.Constant) and last.value.value is Ellipsis:
            continue
        if any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(node)):
            continue
        if last and not isinstance(last, (ast.Return, ast.Raise, ast.If,
                                          ast.For, ast.While, ast.Try,
                                          ast.With, ast.AsyncFor, ast.AsyncWith)):
            # Very heuristic — only flag if the last statement is a bare expr
            if isinstance(last, ast.Expr) and ann not in ("None", ""):
                issues.append(("LOGIC", rel, node.end_lineno or node.lineno,
                               f"def {node.name}() -> {ann}: last stmt is expression, not return"))

# ── Report ────────────────────────────────────────────────────────────────
by_level: dict[str, list] = defaultdict(list)
for sev, f, l, m in issues:
    by_level[sev].append((f, l, m))

print(f"\nTotal issues found: {len(issues)}")
print(f"  SYNTAX  : {len(by_level.get('SYNTAX', []))}")
print(f"  IMPORT  : {len(by_level.get('IMPORT', []))}")
print(f"  UNDEF   : {len(by_level.get('UNDEF', []))}")
print(f"  LOGIC   : {len(by_level.get('LOGIC', []))}")

# Deduplicate and print top issues
def dedup_print(level, limit=40):
    items = by_level.get(level, [])
    if not items:
        return
    seen: set[tuple] = set()
    deduped = []
    for f, l, m in items:
        key = (f, m[:50])
        if key not in seen:
            seen.add(key)
            deduped.append((f, l, m))
    print(f"\n=== {level} ({len(deduped)} unique) ===")
    by_file: dict[str, list] = defaultdict(list)
    for f, l, m in deduped:
        by_file[f].append((l, m))
    count = 0
    for f, items2 in sorted(by_file.items(), key=lambda x: -len(x[1])):
        print(f"  {f}  ({len(items2)} issues)")
        for l, m in items2[:3]:
            print(f"    :{l} {m[:90]}")
        count += 1
        if count >= limit:
            remaining = len(by_file) - count
            if remaining > 0:
                print(f"  ... and {remaining} more files")
            break

dedup_print("SYNTAX")
dedup_print("IMPORT", limit=50)
dedup_print("UNDEF", limit=30)
dedup_print("LOGIC", limit=20)

print("\nDeep audit complete.")
