# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Tests for eval CLI display flags."""

from __future__ import annotations

from click.testing import CliRunner

from vectorcode.src.evals.cli import main

class TestCompactFlag:
    def test_compact_flag_accepted(self):
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert "--compact" in result.output

    def test_trace_detail_flag_accepted(self):
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert "--trace-detail" in result.output
