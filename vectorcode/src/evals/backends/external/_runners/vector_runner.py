# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Subprocess bridge: runs one task through VECTOR agent and emits JSON.

Invoked as:
    python vector_runner.py \\
        --task <prompt> --model <m> --base-url <url> \\
        --api-mode <mode> --output-json <path> [--workspace <path>] \\
        [--max-iterations 90] [--system-prompt <s>]

Imports `AIAgent` from `run_agent` (the top-level module VECTOR ships
at the path indicated by `VECTOR_AGENT_PATH`, set by the calling
backend). Writes a JSON dict matching the `_RunnerOutput` schema in
`_subprocess_runner.py` to `--output-json` before exiting.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-mode", default="chat_completions")
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--workspace", default="")
    parser.add_argument("--max-iterations", type=int, default=90)
    parser.add_argument("--system-prompt", default="")
    args = parser.parse_args()

    output: dict = {
        "content": "",
        "usage": {},
        "trajectory": [],
        "tool_calls": 0,
        "turn_count": 0,
        "error": None,
    }

    vector_path = os.environ.get("VECTOR_AGENT_PATH")
    if not vector_path:
        output["error"] = "VECTOR_AGENT_PATH not set"
        args.output_json.write_text(json.dumps(output))
        return 2
    api_key = os.environ.get("VECTOR_EVAL_API_KEY")
    if not api_key:
        output["error"] = "VECTOR_EVAL_API_KEY not set"
        args.output_json.write_text(json.dumps(output))
        return 2

    sys.path.insert(0, vector_path)

    if args.workspace:
        os.chdir(args.workspace)

    try:
        from run_agent import AIAgent  # type: ignore[import-not-found]
    except ImportError as e:
        output["error"] = f"vector_import_failed: {e}"
        args.output_json.write_text(json.dumps(output))
        return 3

    try:
        agent = AIAgent(
            base_url=args.base_url,
            api_key=api_key,
            model=args.model,
            api_mode=args.api_mode,
            max_iterations=args.max_iterations,
            quiet_mode=True,
            save_trajectories=True,
            platform="vector-eval",
        )
        kwargs = {}
        if args.system_prompt:
            kwargs["system_message"] = args.system_prompt
        result = agent.run_conversation(args.task, **kwargs)

        # Validate that VECTOR returned the expected keys; if not, capture
        # what we actually got so debugging isn't a guessing game.
        if not isinstance(result, dict):
            output["error"] = (
                f"vector_returned_non_dict: type={type(result).__name__}, "
                f"value={str(result)[:200]}"
            )
            args.output_json.write_text(json.dumps(output))
            return 0
        expected_keys = {"final_response", "messages"}
        if not (expected_keys & set(result.keys())):
            output["error"] = (
                f"vector_returned_unexpected_shape: keys={list(result.keys())}"
            )
            args.output_json.write_text(json.dumps(output))
            return 0

        # VECTOR returns {"final_response": str, "messages": [dict, ...]}
        # plus aggregate token counts at the TOP LEVEL of the result dict
        # (see `run_agent.py::AIAgent.run_conversation` — the result dict
        # carries `prompt_tokens`, `completion_tokens`, `total_tokens`,
        # `input_tokens`, `output_tokens` keys, populated from the agent's
        # `session_*_tokens` accumulators). Per-message `usage` dicts are
        # NOT populated by VECTOR, so the previous per-message-sum approach
        # always produced 0.
        messages = result.get("messages", [])

        def _safe_int(v: object) -> int:
            try:
                return int(v or 0)
            except (TypeError, ValueError):
                return 0

        # Primary: top-level aggregate (matches VECTOR's actual return shape).
        prompt_tokens = _safe_int(result.get("prompt_tokens"))
        completion_tokens = _safe_int(result.get("completion_tokens"))

        # Secondary: canonical input/output names (VECTOR also exposes these).
        if not prompt_tokens:
            prompt_tokens = _safe_int(result.get("input_tokens"))
        if not completion_tokens:
            completion_tokens = _safe_int(result.get("output_tokens"))

        # Tertiary: a nested `usage` dict, in case VECTOR's API surface
        # changes shape in a future version.
        if not prompt_tokens or not completion_tokens:
            top_level_usage = result.get("usage")
            if isinstance(top_level_usage, dict):
                if not prompt_tokens:
                    prompt_tokens = _safe_int(
                        top_level_usage.get("prompt_tokens")
                        or top_level_usage.get("input_tokens")
                    )
                if not completion_tokens:
                    completion_tokens = _safe_int(
                        top_level_usage.get("completion_tokens")
                        or top_level_usage.get("output_tokens")
                    )

        # Final fallback: sum per-message usage (works only if VECTOR
        # populates per-turn usage — currently it does not, but keep the
        # path so the bridge degrades gracefully if behaviour changes).
        if not prompt_tokens:
            prompt_tokens = sum(
                _safe_int(m.get("usage", {}).get("prompt_tokens"))
                for m in messages
                if isinstance(m, dict)
            )
        if not completion_tokens:
            completion_tokens = sum(
                _safe_int(m.get("usage", {}).get("completion_tokens"))
                for m in messages
                if isinstance(m, dict)
            )

        # Last-resort: agent instance attribute (run_conversation
        # accumulates into self.session_*_tokens during the call).
        if not prompt_tokens:
            prompt_tokens = _safe_int(getattr(agent, "session_prompt_tokens", 0))
        if not completion_tokens:
            completion_tokens = _safe_int(
                getattr(agent, "session_completion_tokens", 0)
            )

        # Prefer VECTOR's top-level total_tokens if it's been populated;
        # otherwise reconstruct as prompt + completion.
        total_tokens = _safe_int(result.get("total_tokens"))
        if not total_tokens:
            total_tokens = prompt_tokens + completion_tokens

        tool_calls = sum(
            len(m.get("tool_calls", []) or []) for m in messages if isinstance(m, dict)
        )
        turn_count = sum(
            1 for m in messages if isinstance(m, dict) and m.get("role") == "assistant"
        )

        output.update(
            {
                "content": result.get("final_response", ""),
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
                "trajectory": messages,
                "tool_calls": tool_calls,
                "turn_count": turn_count,
                "error": None,
            }
        )
    except Exception as e:
        output["error"] = f"vector_runtime_error: {e}"
        output["trajectory"] = [{"traceback": traceback.format_exc()}]

    args.output_json.write_text(json.dumps(output))
    return 0

if __name__ == "__main__":
    sys.exit(main())
