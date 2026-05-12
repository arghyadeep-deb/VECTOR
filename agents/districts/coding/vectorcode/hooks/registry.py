"""
HookRegistry — VectorCode VC-5.

17 named hooks with priority ordering and per-handler timeout protection.
Each handler runs in a daemon thread; timeouts and exceptions are swallowed
so a slow or crashing hook never blocks or kills the caller.
"""
import sys
import threading
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from loguru import logger


class HookName(Enum):
    PRE_EDIT = "PRE_EDIT"
    POST_EDIT = "POST_EDIT"
    PRE_TASK = "PRE_TASK"
    POST_TASK = "POST_TASK"
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"
    ROUTE = "ROUTE"
    EXPLAIN = "EXPLAIN"
    PRETRAIN = "PRETRAIN"
    BUILD_AGENTS = "BUILD_AGENTS"
    TRANSFER = "TRANSFER"
    TEAMMATE_IDLE = "TEAMMATE_IDLE"
    TASK_COMPLETE = "TASK_COMPLETE"
    NOTIFY = "NOTIFY"
    INTELLIGENCE = "INTELLIGENCE"
    SESSION_RESTORE = "SESSION_RESTORE"
    POST_COMMAND = "POST_COMMAND"


class HookRegistry:
    """
    Central registry for VectorCode lifecycle hooks.

    register()   — attach a callable to a named hook with optional priority.
    unregister() — detach a callable from a hook.
    fire()       — run all handlers for a hook in priority order, each
                   guarded by a daemon thread + timeout.
    list_handlers() — return the ordered list of callables for a hook.
    """

    def __init__(self, default_timeout: float = 5.0) -> None:
        self.default_timeout = default_timeout
        # Each entry: (priority: int, fn: Callable)
        self._handlers: Dict[HookName, List[Tuple[int, Callable]]] = {
            h: [] for h in HookName
        }

    def register(self, hook: HookName, fn: Callable, priority: int = 5) -> None:
        """Attach fn to hook. Lower priority number runs first."""
        self._handlers[hook].append((priority, fn))
        self._handlers[hook].sort(key=lambda x: x[0])
        logger.debug(f"[VECTOR][hooks] registered {hook.name} priority={priority} fn={fn.__name__ if hasattr(fn, '__name__') else fn}")

    def unregister(self, hook: HookName, fn: Callable) -> None:
        """Remove the first registration of fn from hook."""
        self._handlers[hook] = [
            (p, f) for p, f in self._handlers[hook] if f is not fn
        ]
        logger.debug(f"[VECTOR][hooks] unregistered {hook.name}")

    def fire(self, hook: HookName, ctx: dict) -> None:
        """
        Execute all handlers for hook in priority order.
        Each handler runs in a daemon thread with self.default_timeout.
        Timeouts and exceptions are caught and logged — never re-raised.
        """
        for _, fn in self._handlers[hook]:
            exc: List[Exception] = []

            def _run(fn: Callable = fn, exc: List = exc) -> None:
                try:
                    fn(ctx)
                except Exception as e:
                    exc.append(e)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=self.default_timeout)

            if t.is_alive():
                logger.warning(
                    f"[VECTOR][hooks] {hook.name} handler timed out after {self.default_timeout}s — skipping"
                )
            elif exc:
                logger.error(
                    f"[VECTOR][hooks] {hook.name} handler raised: {exc[0]}"
                )

    def list_handlers(self, hook: HookName) -> List[Callable]:
        """Return callables registered to hook in current priority order."""
        return [fn for _, fn in self._handlers[hook]]


if __name__ == "__main__":
    reg = HookRegistry(default_timeout=1.0)

    fired: list = []
    reg.register(HookName.PRE_EDIT, lambda ctx: fired.append(ctx.get("file")), priority=1)
    reg.register(HookName.PRE_EDIT, lambda ctx: fired.append("second"), priority=2)
    reg.fire(HookName.PRE_EDIT, {"file": "main.py"})
    assert fired == ["main.py", "second"], f"unexpected: {fired}"

    reg.unregister(HookName.PRE_EDIT, reg.list_handlers(HookName.PRE_EDIT)[0])
    assert len(reg.list_handlers(HookName.PRE_EDIT)) == 1

    print("registry.py OK")
