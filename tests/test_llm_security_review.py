"""Tests for the LLM semantic security review module.

Preserved from test_skillmd_scanner.py during migration to harness-eval CLI.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from abevalflow.security.llm_review import llm_security_review


class TestLLMSecurityReview:
    """Tests for the llm_security_review function."""

    def test_valid_findings(self, tmp_path):
        """LLM returns valid JSON findings."""
        mock_response = json.dumps(
            [{"check": "anti_jailbreak", "severity": "high", "message": "test", "file_path": "SKILL.md"}]
        )
        (tmp_path / "SKILL.md").write_text("content")
        with patch(
            "abevalflow.llm_client.chat_completion",
            return_value=mock_response,
        ):
            findings = llm_security_review(tmp_path)
        assert len(findings) == 1
        assert findings[0]["source"] == "llm"
        assert findings[0]["rule_id"] == "llm-anti-jailbreak"

    def test_fenced_json_parsed(self, tmp_path):
        """LLM returns JSON wrapped in markdown fences."""
        mock_response = (
            '```json\n[{"check": "semantic_attack", "severity": "critical", '
            '"message": "test", "file_path": "SKILL.md"}]\n```'
        )
        (tmp_path / "SKILL.md").write_text("content")
        with patch(
            "abevalflow.llm_client.chat_completion",
            return_value=mock_response,
        ):
            findings = llm_security_review(tmp_path)
        assert len(findings) == 1

    def test_llm_failure_returns_empty(self, tmp_path):
        """LLM call fails gracefully."""
        (tmp_path / "SKILL.md").write_text("content")
        with patch(
            "abevalflow.llm_client.chat_completion",
            side_effect=Exception("API error"),
        ):
            findings = llm_security_review(tmp_path)
        assert findings == []

    def test_invalid_json_returns_empty(self, tmp_path):
        """LLM returns invalid JSON."""
        (tmp_path / "SKILL.md").write_text("content")
        with patch(
            "abevalflow.llm_client.chat_completion",
            return_value="not json at all",
        ):
            findings = llm_security_review(tmp_path)
        assert findings == []

    def test_no_md_files(self, tmp_path):
        """Empty directory returns no findings."""
        findings = llm_security_review(tmp_path)
        assert findings == []
