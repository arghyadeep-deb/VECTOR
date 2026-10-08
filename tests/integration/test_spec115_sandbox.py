"""Session 11.5 — Skill Execution Sandbox integration tests.

Verifies:
- VectorSandbox isolates and executes Python safely
- PermissionGateway classifies skill action types correctly
- SkillSandboxRunner executes 3 curated representative skills end-to-end:
    sherlock              (security / GREEN)
    dogfood               (general / GREEN)
    systematic-debugging  (execution / YELLOW)
- Forbidden and RED actions are blocked before sandbox runs
- Results are fully captured (stdout, exit code, elapsed time)
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest


# ---------------------------------------------------------------------------
# Helper: run async test bodies synchronously
# Use asyncio.run() — creates a fresh event loop each call, avoiding
# "event loop is closed" errors when the full suite runs multiple files.
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Skill entries for the 3 representative skills
# ---------------------------------------------------------------------------

_SEC_SKILL = {
    "skill_id": "sherlock",
    "category": "security",
    "skill_md_path": "vectorcode/src/skills/optional/security/sherlock/SKILL.md",
    "name": "Sherlock",
}

_GS_SKILL = {
    "skill_id": "dogfood",
    "category": "general",
    "skill_md_path": "vectorcode/src/skills/dogfood/SKILL.md",
    "name": "Dogfood",
}

_EC_SKILL = {
    "skill_id": "systematic-debugging",
    "category": "execution",
    "skill_md_path": "vectorcode/src/skills/software-development/systematic-debugging/SKILL.md",
    "name": "Systematic Debugging",
}

_UNKNOWN_SKILL = {
    "skill_id": "vc-xx-unknown-category",
    "category": "unknown_category",
    "skill_md_path": "",
    "name": "Unknown",
}


# ---------------------------------------------------------------------------
# 1. VectorSandbox isolation tests
# ---------------------------------------------------------------------------

class TestVectorSandboxIsolation(unittest.TestCase):

    def setUp(self):
        from core.sandbox.vector_sandbox import VectorSandbox
        self.sb = VectorSandbox()

    def test_run_python_returns_sandbox_result(self):
        result = _run(self.sb.run_python("print('hello')"))
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_code, 0)

    def test_run_python_captures_stdout(self):
        result = _run(self.sb.run_python("print('vector_output_42')"))
        self.assertIn("vector_output_42", result.stdout)

    def test_run_code_safe_wraps_errors(self):
        result = _run(self.sb.run_code_safe("raise ValueError('intentional')"))
        self.assertFalse(result.success)
        self.assertIn("ValueError", result.stderr)

    def test_run_code_safe_success(self):
        result = _run(self.sb.run_code_safe("x = 2 + 2\nprint(x)"))
        self.assertTrue(result.success)
        self.assertIn("4", result.stdout)

    def test_sandbox_result_has_elapsed(self):
        result = _run(self.sb.run_python("pass"))
        self.assertGreater(result.elapsed_secs, 0.0)

    def test_sandbox_result_has_exit_code(self):
        result = _run(self.sb.run_python("import sys; sys.exit(0)"))
        self.assertEqual(result.exit_code, 0)

    def test_sandbox_timeout_triggers(self):
        # Short timeout to confirm timed_out flag is set when exceeded
        result = _run(self.sb.run_python("import time; time.sleep(60)", timeout=1.0))
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)

    def test_sandbox_json_output(self):
        code = "import json; print(json.dumps({'status': 'ok', 'value': 99}))"
        result = _run(self.sb.run_python(code))
        self.assertTrue(result.success)
        data = json.loads(result.stdout.strip())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["value"], 99)


# ---------------------------------------------------------------------------
# 2. PermissionGateway classification for skill action types
# ---------------------------------------------------------------------------

class TestGatewayClassifiesSkillActions(unittest.TestCase):

    def setUp(self):
        from core.loop.permission_gateway import PermissionGateway
        self.gw = PermissionGateway()

    def test_analyze_code_is_green(self):
        self.assertEqual(self.gw._classify("analyze_code"), "GREEN")

    def test_read_code_is_green(self):
        self.assertEqual(self.gw._classify("read_code"), "GREEN")

    def test_run_tests_is_yellow(self):
        self.assertEqual(self.gw._classify("run_tests"), "YELLOW")

    def test_execute_code_is_red(self):
        self.assertEqual(self.gw._classify("execute_code"), "RED")

    def test_mass_delete_is_forbidden(self):
        self.assertEqual(self.gw._classify("mass_delete"), "FORBIDDEN")

    def test_unknown_type_is_unknown(self):
        self.assertEqual(self.gw._classify("totally_made_up_action"), "UNKNOWN")


# ---------------------------------------------------------------------------
# 3. SkillSandboxRunner — classify_skill
# ---------------------------------------------------------------------------

class TestSkillSandboxRunnerClassify(unittest.TestCase):

    def setUp(self):
        from core.sandbox.skill_sandbox import SkillSandboxRunner
        self.runner = SkillSandboxRunner()

    def test_security_category_maps_to_green(self):
        _, level = self.runner.classify_skill("security")
        self.assertEqual(level, "GREEN")

    def test_general_category_maps_to_green(self):
        _, level = self.runner.classify_skill("general")
        self.assertEqual(level, "GREEN")

    def test_execution_category_maps_to_yellow(self):
        _, level = self.runner.classify_skill("execution")
        self.assertEqual(level, "YELLOW")

    def test_unknown_category_maps_to_red(self):
        # Unknown categories fall back to execute_code → RED
        _, level = self.runner.classify_skill("unknown_category")
        self.assertEqual(level, "RED")

    def test_classify_returns_action_and_level_tuple(self):
        result = self.runner.classify_skill("security")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        action, level = result
        self.assertIsInstance(action, str)
        self.assertIsInstance(level, str)


# ---------------------------------------------------------------------------
# 4. SkillSandboxRunner — execute vc-sec-* (security / GREEN)
# ---------------------------------------------------------------------------

class TestSecuritySkillExecution(unittest.TestCase):

    def setUp(self):
        from core.sandbox.skill_sandbox import SkillSandboxRunner
        self.runner = SkillSandboxRunner()

    def test_sec_skill_executes_successfully(self):
        result = _run(self.runner.execute_skill(_SEC_SKILL))
        self.assertTrue(result.succeeded, f"skill did not succeed: {result.error or result.sandbox_result}")

    def test_sec_skill_permission_level_is_green(self):
        result = _run(self.runner.execute_skill(_SEC_SKILL))
        self.assertEqual(result.permission_level, "GREEN")

    def test_sec_skill_is_approved(self):
        result = _run(self.runner.execute_skill(_SEC_SKILL))
        self.assertTrue(result.approved)

    def test_sec_skill_sandbox_result_captured(self):
        result = _run(self.runner.execute_skill(_SEC_SKILL))
        self.assertIsNotNone(result.sandbox_result)
        self.assertGreater(result.sandbox_result.elapsed_secs, 0.0)

    def test_sec_skill_stdout_is_valid_json(self):
        result = _run(self.runner.execute_skill(_SEC_SKILL))
        data = json.loads(result.sandbox_result.stdout.strip())
        self.assertEqual(data["skill_id"], "sherlock")
        self.assertEqual(data["category"], "security")
        self.assertEqual(data["status"], "verified")

    def test_sec_skill_md_exists_true(self):
        result = _run(self.runner.execute_skill(_SEC_SKILL))
        data = json.loads(result.sandbox_result.stdout.strip())
        self.assertTrue(data["md_exists"], "SKILL.md was not found in sandbox")
        self.assertGreater(data["md_size"], 0)


# ---------------------------------------------------------------------------
# 5. SkillSandboxRunner — execute vc-gs-* (general / GREEN)
# ---------------------------------------------------------------------------

class TestGeneralSkillExecution(unittest.TestCase):

    def setUp(self):
        from core.sandbox.skill_sandbox import SkillSandboxRunner
        self.runner = SkillSandboxRunner()

    def test_gs_skill_executes_successfully(self):
        result = _run(self.runner.execute_skill(_GS_SKILL))
        self.assertTrue(result.succeeded)

    def test_gs_skill_permission_level_is_green(self):
        result = _run(self.runner.execute_skill(_GS_SKILL))
        self.assertEqual(result.permission_level, "GREEN")

    def test_gs_skill_stdout_is_valid_json(self):
        result = _run(self.runner.execute_skill(_GS_SKILL))
        data = json.loads(result.sandbox_result.stdout.strip())
        self.assertEqual(data["skill_id"], "dogfood")
        self.assertEqual(data["status"], "verified")

    def test_gs_skill_md_exists_true(self):
        result = _run(self.runner.execute_skill(_GS_SKILL))
        data = json.loads(result.sandbox_result.stdout.strip())
        self.assertTrue(data["md_exists"])

    def test_gs_skill_no_error(self):
        result = _run(self.runner.execute_skill(_GS_SKILL))
        self.assertIsNone(result.error)


# ---------------------------------------------------------------------------
# 6. SkillSandboxRunner — execute vc-ec-* (execution / YELLOW)
# ---------------------------------------------------------------------------

class TestExecutionSkillExecution(unittest.TestCase):

    def setUp(self):
        from core.sandbox.skill_sandbox import SkillSandboxRunner
        self.runner = SkillSandboxRunner()

    def test_ec_skill_executes_successfully(self):
        result = _run(self.runner.execute_skill(_EC_SKILL))
        self.assertTrue(result.succeeded)

    def test_ec_skill_permission_level_is_yellow(self):
        result = _run(self.runner.execute_skill(_EC_SKILL))
        self.assertEqual(result.permission_level, "YELLOW")

    def test_ec_skill_is_approved(self):
        # YELLOW is approved — owner is notified but execution proceeds
        result = _run(self.runner.execute_skill(_EC_SKILL))
        self.assertTrue(result.approved)

    def test_ec_skill_stdout_is_valid_json(self):
        result = _run(self.runner.execute_skill(_EC_SKILL))
        data = json.loads(result.sandbox_result.stdout.strip())
        self.assertEqual(data["skill_id"], "systematic-debugging")
        self.assertEqual(data["category"], "execution")
        self.assertEqual(data["status"], "verified")

    def test_ec_skill_md_exists_true(self):
        result = _run(self.runner.execute_skill(_EC_SKILL))
        data = json.loads(result.sandbox_result.stdout.strip())
        self.assertTrue(data["md_exists"])
        self.assertGreater(data["md_size"], 0)


# ---------------------------------------------------------------------------
# 7. Gateway enforcement — RED and FORBIDDEN blocked
# ---------------------------------------------------------------------------

class TestGatewayEnforcement(unittest.TestCase):

    def setUp(self):
        from core.sandbox.skill_sandbox import SkillSandboxRunner
        self.runner = SkillSandboxRunner()

    def test_red_skill_is_not_approved(self):
        # Unknown category → execute_code → RED
        result = _run(self.runner.execute_skill(_UNKNOWN_SKILL))
        self.assertFalse(result.approved)

    def test_red_skill_sandbox_not_run(self):
        result = _run(self.runner.execute_skill(_UNKNOWN_SKILL))
        self.assertIsNone(result.sandbox_result)

    def test_red_skill_has_error_message(self):
        result = _run(self.runner.execute_skill(_UNKNOWN_SKILL))
        self.assertIsNotNone(result.error)
        self.assertIn("approval", result.error.lower())

    def test_red_skill_permission_level_is_red(self):
        result = _run(self.runner.execute_skill(_UNKNOWN_SKILL))
        self.assertEqual(result.permission_level, "RED")

    def test_forbidden_action_blocked(self):
        from core.loop.permission_gateway import PermissionGateway
        gw = PermissionGateway()
        self.assertEqual(gw._classify("mass_delete"), "FORBIDDEN")
        self.assertEqual(gw._classify("format_drive"), "FORBIDDEN")

    def test_sandbox_result_succeeded_false_when_not_approved(self):
        result = _run(self.runner.execute_skill(_UNKNOWN_SKILL))
        self.assertFalse(result.succeeded)


# ---------------------------------------------------------------------------
# 8. Batch execution and result capture
# ---------------------------------------------------------------------------

class TestBatchExecution(unittest.TestCase):

    def setUp(self):
        from core.sandbox.skill_sandbox import SkillSandboxRunner
        self.runner = SkillSandboxRunner()

    def test_batch_executes_all_three_skills(self):
        results = _run(self.runner.execute_batch([_SEC_SKILL, _GS_SKILL, _EC_SKILL]))
        self.assertEqual(len(results), 3)

    def test_batch_all_succeed(self):
        results = _run(self.runner.execute_batch([_SEC_SKILL, _GS_SKILL, _EC_SKILL]))
        for r in results:
            self.assertTrue(r.succeeded, f"{r.skill_id} did not succeed: {r.error}")

    def test_batch_results_have_correct_skill_ids(self):
        results = _run(self.runner.execute_batch([_SEC_SKILL, _GS_SKILL, _EC_SKILL]))
        ids = {r.skill_id for r in results}
        self.assertIn("sherlock", ids)
        self.assertIn("dogfood", ids)
        self.assertIn("systematic-debugging", ids)

    def test_batch_results_json_parseable(self):
        results = _run(self.runner.execute_batch([_SEC_SKILL, _GS_SKILL, _EC_SKILL]))
        for r in results:
            if r.sandbox_result and r.sandbox_result.stdout.strip():
                data = json.loads(r.sandbox_result.stdout.strip())
                self.assertIn("status", data)
                self.assertEqual(data["status"], "verified")

    def test_batch_mixed_approved_and_blocked(self):
        results = _run(self.runner.execute_batch([_SEC_SKILL, _UNKNOWN_SKILL]))
        approved = [r for r in results if r.approved]
        blocked = [r for r in results if not r.approved]
        self.assertEqual(len(approved), 1)
        self.assertEqual(len(blocked), 1)


if __name__ == "__main__":
    unittest.main()
