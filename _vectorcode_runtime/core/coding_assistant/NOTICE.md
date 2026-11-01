# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
Its structure suggests a coding-CLI agent framework, but the exact upstream project is unconfirmed.
No root README or LICENSE naming an upstream project was found in this vendored tree.
This notice therefore does not assert an exact upstream project name.
Its advertised `core/programmatic.py` entrypoint does not successfully import in this environment.
That entrypoint is not what VECTOR calls.
VECTOR instead uses `core.tools.builtins`, `core.hooks.manager`, `core.skills.manager`, and `core.paths`.
Vendored as-is; VECTOR's own code calls into: `districts/coding/coding_tools.py`.
