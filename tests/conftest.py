from __future__ import annotations

import os
import tempfile
from pathlib import Path


_TEST_DATA_DIR = Path(tempfile.gettempdir()) / "vector_pytest_data"
os.environ.setdefault("VECTOR_TEST_DATA_DIR", str(_TEST_DATA_DIR))
