"""Regression for 4 vectorcode/src/{vc_agents,connectors}/ files that imported
loguru correctly, then immediately shadowed it with
``logger = logging.getLogger(__name__)`` -- silently breaking every
``{}``-style loguru placeholder in that file (stdlib's %-style silently fails
under loguru's formatter):

- vectorcode/src/vc_agents/operative.py
- vectorcode/src/connectors/apple_health.py
- vectorcode/src/connectors/embedding_store.py
- vectorcode/src/connectors/retriever.py

Also covers a second bug found in operative.py: four ``except Exception:``
handlers swallowed the real exception without capturing or logging it at
all (a generic "could not do X for operator Y" message with no error
detail) -- now captures ``as e`` and logs it.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

FILES = [
    "vectorcode/src/vc_agents/operative.py",
    "vectorcode/src/connectors/apple_health.py",
    "vectorcode/src/connectors/embedding_store.py",
    "vectorcode/src/connectors/retriever.py",
]


@pytest.mark.parametrize("path", FILES)
def test_loguru_import_is_not_shadowed_by_stdlib_logging(path):
    src = Path(path).read_text(encoding="utf-8")
    assert "from loguru import logger" in src, f"{path} should still import loguru"
    # The bug shape: `from loguru import logger` immediately overwritten by
    # `logger = logging.getLogger(__name__)` a few lines later.
    assert not re.search(r"^logger\s*=\s*logging\.getLogger", src, re.MULTILINE), (
        f"{path} still shadows the loguru `logger` with a stdlib logging.Logger"
    )


@pytest.mark.parametrize(
    "module_name,path",
    [
        ("vc_agents.operative", "vectorcode/src/vc_agents/operative.py"),
        ("connectors.apple_health", "vectorcode/src/connectors/apple_health.py"),
        ("connectors.embedding_store", "vectorcode/src/connectors/embedding_store.py"),
        ("connectors.retriever", "vectorcode/src/connectors/retriever.py"),
    ],
)
def test_no_leftover_percent_style_logger_placeholders(module_name, path):
    import re

    src = Path(path).read_text(encoding="utf-8")
    # crude but effective: a logger.X("...%s/%d/%r...", ...) call
    calls = re.findall(r"logger\.(?:info|warning|error|debug|critical)\(\s*\"[^\"]*%[sdr]", src)
    assert calls == [], f"found stdlib-style placeholders still present: {calls}"


def test_operative_except_blocks_capture_and_log_the_real_exception():
    # operative.py's _recall_state/_load_session/_save_session/
    # _auto_persist_state each had `except Exception:` with no captured
    # variable, logging only a generic "could not do X for operator Y"
    # message -- the real exception detail was discarded entirely. Not
    # importing the module here: AgentRegistry.register() raises if the
    # same key is registered twice in one process, and this file is
    # imported elsewhere in the suite under a different sys.path alias,
    # so a fresh import here is test-order-dependent. Static check instead.
    src = Path("vectorcode/src/vc_agents/operative.py").read_text(encoding="utf-8")
    bare_swallows = re.findall(r"except Exception:\n\s+logger\.debug\(", src)
    assert bare_swallows == [], (
        "found except Exception: blocks that log without capturing the "
        f"exception: {len(bare_swallows)} occurrence(s)"
    )
    assert src.count("except Exception as e:") >= 4


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
