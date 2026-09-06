"""Tests for OpenShellRunner in scripts/run_aeh.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from scripts.run_aeh import RUNNERS, OpenShellRunner, RunnerError, get_runner


class TestOpenShellRunnerRegistry:
    def test_openshell_runner_registered(self):
        assert "openshell" in RUNNERS
        assert RUNNERS["openshell"] is OpenShellRunner

    def test_get_runner_openshell(self):
        runner = get_runner("openshell", model="claude-sonnet")
        assert isinstance(runner, OpenShellRunner)
        assert runner.name == "openshell"
        assert runner.model == "claude-sonnet"


class TestOpenShellRunnerExecute:
    def test_requires_model(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_EVAL_OPENSHELL_IMAGE", "quay.io/example/openclaw:latest")
        monkeypatch.setenv("OPENSHELL_GATEWAY_ENDPOINT", "https://gw.example:17670")
        runner = OpenShellRunner()
        config = tmp_path / "eval.yaml"
        config.write_text(yaml.dump({"skill": "demo"}))
        with pytest.raises(RunnerError, match="--model"):
            runner.run_single(config, tmp_path / "reports" / "demo" / "run-1")

    def test_requires_sandbox_image(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AGENT_EVAL_OPENSHELL_IMAGE", raising=False)
        monkeypatch.setenv("OPENSHELL_GATEWAY_ENDPOINT", "https://gw.example:17670")
        runner = OpenShellRunner(model="claude-sonnet")
        config = tmp_path / "eval.yaml"
        config.write_text(yaml.dump({"skill": "demo"}))
        with pytest.raises(RunnerError, match="AGENT_EVAL_OPENSHELL_IMAGE"):
            runner.run_single(config, tmp_path / "reports" / "demo" / "run-1")

    def test_requires_gateway_endpoint(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_EVAL_OPENSHELL_IMAGE", "quay.io/example/openclaw:latest")
        monkeypatch.delenv("OPENSHELL_GATEWAY_ENDPOINT", raising=False)
        runner = OpenShellRunner(model="claude-sonnet")
        config = tmp_path / "eval.yaml"
        config.write_text(yaml.dump({"skill": "demo"}))
        with pytest.raises(RunnerError, match="OPENSHELL_GATEWAY_ENDPOINT"):
            runner.run_single(config, tmp_path / "reports" / "demo" / "run-1")

    @patch("subprocess.run")
    def test_execute_command_shape(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_EVAL_OPENSHELL_IMAGE", "quay.io/example/openclaw:latest")
        monkeypatch.setenv(
            "OPENSHELL_GATEWAY_ENDPOINT",
            "https://abeval-saw-gateway.forge-saw.svc.cluster.local:17670",
        )
        mock_run.return_value = MagicMock(returncode=0)

        reports = tmp_path / "reports"
        output = reports / "openclaw-forge" / "run-1"
        config = tmp_path / "eval.yaml"
        config.write_text(yaml.dump({"skill": "openclaw-forge", "runner": {"type": "openclaw"}}))

        runner = OpenShellRunner(model="claude-sonnet")
        assert runner.run_single(config, output, run_id="run-1") == 0

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        env = mock_run.call_args.kwargs.get("env") or mock_run.call_args[1].get("env")

        assert "-m" in cmd
        assert "agent_eval.openshell.run" in cmd
        assert "--config" in cmd
        assert str(config) in cmd
        assert "--model" in cmd
        assert "claude-sonnet" in cmd
        assert "--run-id" in cmd
        assert "run-1" in cmd
        assert "agent_eval.harbor.run" not in cmd
        assert env["AGENT_EVAL_RUNS_DIR"] == str(reports)
        assert Path(env["AGENT_EVAL_RUNS_DIR"]) == output.parent.parent
