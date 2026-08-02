"""Tests for scripts/log_aeh_mlflow.py."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.log_aeh_mlflow import main


def _write_run(tmp_path: Path, *, skill: str = "demo-skill", run_id: str = "run-1") -> tuple[Path, Path]:
    runs = tmp_path / "reports"
    run_dir = runs / skill / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_result.json").write_text(
        json.dumps(
            {
                "execution_mode": "harbor",
                "mean_reward": 0.8,
                "cost_usd": 0.12,
                "token_usage": {"input": 100, "output": 50},
                "model": "claude-sonnet",
            }
        )
    )
    (run_dir / "summary.yaml").write_text(yaml.safe_dump({"mean_reward": 0.8}))
    config = tmp_path / "eval.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "skill": skill,
                "mlflow": {"experiment": "aeh-demo"},
                "models": {"skill": "claude-sonnet"},
                "judges": [{"name": "ok", "check": "return True, 'ok'"}],
            }
        )
    )
    return runs, config


def test_skips_when_disabled(tmp_path: Path) -> None:
    runs, config = _write_run(tmp_path)
    rc = main(
        [
            "--run-id",
            "run-1",
            "--config",
            str(config),
            "--runs-dir",
            str(runs),
            "--tracking-uri",
            "http://mlflow.example:5000",
            "--enabled",
            "false",
        ]
    )
    assert rc == 0


def test_skips_when_uri_empty(tmp_path: Path) -> None:
    runs, config = _write_run(tmp_path)
    rc = main(
        [
            "--run-id",
            "run-1",
            "--config",
            str(config),
            "--runs-dir",
            str(runs),
            "--tracking-uri",
            "",
            "--enabled",
            "true",
        ]
    )
    assert rc == 0


def test_returns_error_when_mlflow_not_importable(tmp_path: Path, monkeypatch) -> None:
    runs, config = _write_run(tmp_path)
    import builtins

    real_import = builtins.__import__

    def _block_mlflow(name, *args, **kwargs):
        if name == "mlflow" or name.startswith("mlflow."):
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_mlflow)
    rc = main(
        [
            "--run-id",
            "run-1",
            "--config",
            str(config),
            "--runs-dir",
            str(runs),
            "--tracking-uri",
            "http://mlflow.example:5000",
            "--enabled",
            "true",
            "--actions",
            "log-results",
        ]
    )
    assert rc == 1


def test_minimal_logger_with_mock_mlflow(tmp_path: Path, monkeypatch) -> None:
    runs, config = _write_run(tmp_path)

    class _FakeRun:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    calls: dict[str, list] = {"params": [], "metrics": [], "artifacts": []}

    class _FakeMlflow:
        def set_tracking_uri(self, uri):
            calls["uri"] = uri

        def set_experiment(self, name):
            calls["experiment"] = name

        def start_run(self, run_name=None):
            calls["run_name"] = run_name
            return _FakeRun()

        def log_param(self, k, v):
            calls["params"].append((k, v))

        def log_metric(self, k, v):
            calls["metrics"].append((k, v))

        def log_artifact(self, path):
            calls["artifacts"].append(path)

    import sys

    monkeypatch.setitem(sys.modules, "mlflow", _FakeMlflow())

    # Restrict to log-results so missing AEH push/sync scripts do not matter.
    monkeypatch.setattr(
        "scripts.log_aeh_mlflow._resolve_log_results_script",
        lambda: None,
    )
    rc = main(
        [
            "--run-id",
            "run-1",
            "--config",
            str(config),
            "--runs-dir",
            str(runs),
            "--tracking-uri",
            "http://mlflow.example:5000",
            "--enabled",
            "true",
            "--actions",
            "log-results",
        ]
    )
    assert rc == 0
    assert calls["uri"] == "http://mlflow.example:5000"
    assert calls["experiment"] == "aeh-demo"
    assert ("mean_reward", 0.8) in calls["metrics"]
    assert ("tokens_input", 100.0) in calls["metrics"]


def test_default_schema_mapping_from_input_yaml(tmp_path: Path) -> None:
    from scripts.log_aeh_mlflow import _default_schema_mapping

    config = tmp_path / "eval.yaml"
    cases = tmp_path / "cases" / "case-001"
    cases.mkdir(parents=True)
    (cases / "input.yaml").write_text(yaml.safe_dump({"prompt": "hello"}))
    (cases / "reference.md").write_text("gold\n")
    config.write_text(yaml.safe_dump({"skill": "demo", "dataset": {"path": "cases"}}))
    mapping = _default_schema_mapping(config)
    assert mapping is not None
    assert mapping["inputs"]["prompt"] == "input.yaml:prompt"
    assert mapping["expectations"]["reference"] == "reference.md:__file__"


def test_upstream_noop_missing_mlflow_markers() -> None:
    from scripts.log_aeh_mlflow import _upstream_noop_missing_mlflow

    assert _upstream_noop_missing_mlflow("MLflow not installed\n") is True
    assert _upstream_noop_missing_mlflow("No module named 'mlflow'\n") is True
    assert _upstream_noop_missing_mlflow("Logged 3 runs\n") is False


def test_run_aeh_log_results_detects_missing_mlflow_noop(tmp_path: Path, monkeypatch) -> None:
    from scripts import log_aeh_mlflow as mod

    script = tmp_path / "log_results.py"
    script.write_text("# stub\n")

    class _Result:
        returncode = 0
        stdout = "MLflow not installed — skipping\n"
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result())
    rc = mod._run_aeh_log_results(
        script=script,
        run_id="run-1",
        config=tmp_path / "eval.yaml",
        runs_dir=tmp_path / "reports",
    )
    assert rc == 2


def test_resolve_run_dir_prefers_exact_then_pairwise_prefixes(tmp_path: Path) -> None:
    from scripts.log_aeh_mlflow import _resolve_run_dir

    skill = "demo-skill"
    runs = tmp_path / "reports"
    exact = runs / skill / "run-1"
    exact.mkdir(parents=True)
    assert _resolve_run_dir(runs, skill, "run-1") == exact

    bare_id = "pipe-abc"
    treatment = runs / skill / f"treatment-{bare_id}"
    treatment.mkdir(parents=True)
    assert _resolve_run_dir(runs, skill, bare_id) == treatment

    control_only = "pipe-ctrl"
    control = runs / skill / f"control-{control_only}"
    control.mkdir(parents=True)
    assert _resolve_run_dir(runs, skill, control_only) == control

    try:
        _resolve_run_dir(runs, skill, "missing-run")
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "missing-run" in str(exc)
