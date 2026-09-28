# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
Its own project metadata says `name = "backend"` and `version = "0.9.79"`.
That metadata declares a FastAPI dependency, consistent with a standalone FastAPI backend.
No upstream project name or license is declared in this `pyproject.toml`.
This notice does not represent the backend as native VECTOR code.
VECTOR starts its `main.py` process and provides a proxy route to that process.
Those are integration points, not a claim that all backend functionality is used.
Vendored as-is; VECTOR's own code calls into: `run_vector.py` and `core/api/routers/sb.py`.
