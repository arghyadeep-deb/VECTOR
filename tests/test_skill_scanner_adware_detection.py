"""
docs/repo_analysis kickbacks.ai's own "Recommendation For Sonnet": add a
clean-room SkillSpector rule category that detects extensions/plugins that
inject ad/sponsored content or hidden telemetry into agent UI surfaces.

Confirmed via re-audit (2026-06-23) that this rule already existed in
core/security/skill_scanner.py (_KICKBACKS_STYLE regex, "extension_adware"
category) — it just had zero test coverage anywhere in the suite, so its
correctness had never actually been verified. This file closes that gap;
no detection logic was changed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_detects_ad_injection_near_extension_hook():
    from core.security.skill_scanner import SkillScanner, FindingSeverity

    text = (
        "This extension adds ad-injection into the spinner hook.\n"
        "It tracks impressions for monetization via a kill-switch.\n"
    )
    findings = SkillScanner()._scan_text(text, "fake.md")
    categories = {f.category for f in findings}
    assert "extension_adware" in categories
    adware = next(f for f in findings if f.category == "extension_adware")
    assert adware.severity == FindingSeverity.HIGH


def test_detects_claude_config_mutation_with_sponsored_prompt():
    from core.security.skill_scanner import SkillScanner

    text = "Modifies claude_config to insert a sponsored prompt into the agent."
    findings = SkillScanner()._scan_text(text, "fake.py")
    assert any(f.category == "extension_adware" for f in findings)


def test_clean_text_does_not_trigger_adware_finding():
    from core.security.skill_scanner import SkillScanner

    text = "This skill fetches weather data and formats it as Markdown."
    findings = SkillScanner()._scan_text(text, "fake.md")
    assert not any(f.category == "extension_adware" for f in findings)


def test_scan_artifact_flags_kickbacks_style_repo_as_caution_or_worse(tmp_path):
    from core.security.skill_scanner import scan_artifact, ArtifactVerdict

    target = tmp_path / "SKILL.md"
    target.write_text(
        "# Sponsored Helper\n\n"
        "Injects sponsored prompt text into the codex_config spinner hook, "
        "with telemetry and a kill-switch for impression tracking.\n",
        encoding="utf-8",
    )
    report = scan_artifact(target)
    assert report.verdict in (ArtifactVerdict.CAUTION, ArtifactVerdict.DO_NOT_LOAD)
    assert any(f.category == "extension_adware" for f in report.findings)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
