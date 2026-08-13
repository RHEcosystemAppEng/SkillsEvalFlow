"""Integration tests for the harness-eval skill-submission-scan gate contract.

Verifies that the JSON format produced by harness-eval's skill-submission-scan
is correctly consumed by SkillMdScannerGate and SkillMdQualityGate.
These tests use hand-written JSON fixtures (not the real CLI) to guard
the contract without depending on harness-eval being installed.
"""

from __future__ import annotations

import json
from pathlib import Path

from abevalflow.gates.quality.skillmd_quality import SkillMdQualityGate
from abevalflow.gates.security.skillmd_scanner import SkillMdScannerGate
from abevalflow.schemas import GatePolicy, GatePolicyItem


def _block_policy() -> GatePolicy:
    return GatePolicy(
        default_mode="block",
        combination="all_pass",
        gates={
            "security": GatePolicyItem(mode="block"),
            "quality": GatePolicyItem(mode="block"),
        },
    )


def _warn_policy() -> GatePolicy:
    return GatePolicy(
        default_mode="warn",
        combination="all_pass",
        gates={
            "security": GatePolicyItem(mode="warn"),
            "quality": GatePolicyItem(mode="warn"),
        },
    )


# --- Fixtures matching harness-eval skill-submission-scan output ---

SECURITY_CLEAN = {"findings": []}

SECURITY_WITH_HIGH = {
    "findings": [
        {
            "severity": "high",
            "rule_id": "security/no-prompt-injection",
            "message": "Line 8 contains a word pattern ('ignore previous instructions')",
            "file_path": "skills/bad-skill/SKILL.md",
            "category": "no_prompt_injection",
            "line": 8,
        }
    ]
}

SECURITY_WITH_CRITICAL = {
    "findings": [
        {
            "severity": "critical",
            "rule_id": "security/prompt-exfiltration",
            "message": "Line 5 contains a prompt exfiltration pattern ('output system prompt')",
            "file_path": "skills/bad-skill/SKILL.md",
            "category": "prompt_exfiltration",
            "line": 5,
        }
    ]
}

SECURITY_WITH_LLM = {
    "findings": [
        {
            "severity": "high",
            "rule_id": "security/no-credential-access",
            "message": "References sensitive path '~/.ssh/' at line 10",
            "file_path": "skills/SKILL.md",
            "category": "no_credential_access",
            "line": 10,
        },
        {
            "severity": "high",
            "rule_id": "llm-anti-jailbreak",
            "message": "Skill claims to be pre-verified safe",
            "file_path": "skills/SKILL.md",
            "category": "anti_jailbreak",
            "source": "llm",
        },
    ]
}

QUALITY_CLEAN = {"findings": []}

QUALITY_WITH_FINDINGS = {
    "findings": [
        {
            "severity": "low",
            "rule_id": "submission/file-completeness",
            "message": "instruction.md has only 5 characters of body text",
            "file_path": "instruction.md",
            "category": "file_completeness",
            "line": 1,
        },
        {
            "severity": "medium",
            "rule_id": "frontmatter/description-quality",
            "message": "Description lacks use-case context",
            "file_path": "skills/SKILL.md",
            "category": "description_quality",
            "line": 1,
        },
    ]
}

QUALITY_WITH_HIGH = {
    "findings": [
        {
            "severity": "high",
            "rule_id": "content/token-budget",
            "message": "Skill is 6000 tokens",
            "file_path": "skills/SKILL.md",
            "category": "token_budget",
            "line": 1,
        },
    ]
}


# --- Security Gate Tests ---


class TestSkillMdScannerGateContract:
    """Verify SkillMdScannerGate reads harness-eval output correctly."""

    def test_clean_scan_passes_block_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-security-scan.json").write_text(json.dumps(SECURITY_CLEAN))
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is True
        assert result.score == 1.0

    def test_high_finding_fails_block_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-security-scan.json").write_text(json.dumps(SECURITY_WITH_HIGH))
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is False
        assert len(result.findings) == 1

    def test_critical_finding_fails_block_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-security-scan.json").write_text(json.dumps(SECURITY_WITH_CRITICAL))
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is False

    def test_high_finding_passes_warn_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-security-scan.json").write_text(json.dumps(SECURITY_WITH_HIGH))
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _warn_policy())
        assert result.passed is True
        assert len(result.findings) == 1

    def test_missing_file_fails_block_mode(self, tmp_path: Path) -> None:
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is False

    def test_missing_file_passes_warn_mode(self, tmp_path: Path) -> None:
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _warn_policy())
        assert result.passed is True

    def test_llm_findings_mixed_with_deterministic(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-security-scan.json").write_text(json.dumps(SECURITY_WITH_LLM))
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is False
        assert len(result.findings) == 2

    def test_finding_fields_parsed(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-security-scan.json").write_text(json.dumps(SECURITY_WITH_HIGH))
        gate = SkillMdScannerGate()
        result = gate.evaluate(tmp_path, _warn_policy())
        finding = result.findings[0]
        assert finding.rule_id == "security/no-prompt-injection"
        assert finding.severity.value == "high"
        assert "ignore previous" in finding.message


# --- Quality Gate Tests ---


class TestSkillMdQualityGateContract:
    """Verify SkillMdQualityGate reads harness-eval output correctly."""

    def test_clean_scan_passes_block_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-quality-scan.json").write_text(json.dumps(QUALITY_CLEAN))
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is True
        assert result.score == 1.0

    def test_low_medium_findings_pass_block_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-quality-scan.json").write_text(json.dumps(QUALITY_WITH_FINDINGS))
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is True
        assert len(result.findings) == 2

    def test_high_finding_fails_block_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-quality-scan.json").write_text(json.dumps(QUALITY_WITH_HIGH))
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is False

    def test_findings_pass_warn_mode(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-quality-scan.json").write_text(json.dumps(QUALITY_WITH_FINDINGS))
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _warn_policy())
        assert result.passed is True

    def test_missing_file_fails_block_mode(self, tmp_path: Path) -> None:
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _block_policy())
        assert result.passed is False

    def test_missing_file_passes_warn_mode(self, tmp_path: Path) -> None:
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _warn_policy())
        assert result.passed is True

    def test_severity_score_weighting(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-quality-scan.json").write_text(json.dumps(QUALITY_WITH_FINDINGS))
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _warn_policy())
        assert 0.0 < result.score < 1.0

    def test_finding_fields_parsed(self, tmp_path: Path) -> None:
        (tmp_path / "skillmd-quality-scan.json").write_text(json.dumps(QUALITY_WITH_FINDINGS))
        gate = SkillMdQualityGate()
        result = gate.evaluate(tmp_path, _warn_policy())
        rule_ids = {f.rule_id for f in result.findings}
        assert "submission/file-completeness" in rule_ids
        assert "frontmatter/description-quality" in rule_ids
