"""Tests for scripts/run_aeh_regression.py."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.run_aeh_regression import main


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "eval.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "skill": "demo",
                "thresholds": {"correctness": {"min_mean": 0.7}},
                "judges": [{"name": "correctness", "check": "return True, 'ok'"}],
            }
        )
    )
    return config


def test_skips_when_disabled(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    rc = main(
        [
            "--run-id",
            "r1",
            "--config",
            str(config),
            "--runs-dir",
            str(tmp_path / "reports"),
            "--enabled",
            "false",
        ]
    )
    assert rc == 0


def test_skips_when_score_py_missing(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    monkeypatch.delenv("AGENT_EVAL_HARNESS_ROOT", raising=False)
    monkeypatch.setattr(
        "scripts.run_aeh_regression._resolve_score_script",
        lambda: None,
    )
    rc = main(
        [
            "--run-id",
            "r1",
            "--config",
            str(config),
            "--runs-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert rc == 0


def test_advisory_exit_zero_when_score_fails(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    fake = tmp_path / "score.py"
    fake.write_text("import sys; print('REGRESSIONS: 1 detected'); sys.exit(1)\n")
    monkeypatch.setattr(
        "scripts.run_aeh_regression._resolve_score_script",
        lambda: fake,
    )
    out = tmp_path / "regression.txt"
    rc = main(
        [
            "--run-id",
            "r1",
            "--config",
            str(config),
            "--runs-dir",
            str(tmp_path / "reports"),
            "--output",
            str(out),
            "--baseline",
            "prior-run",
        ]
    )
    assert rc == 0
    text = out.read_text()
    assert "REGRESSIONS: 1 detected" in text
    assert "baseline=prior-run" in text


def test_strict_propagates_failure(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    fake = tmp_path / "score.py"
    fake.write_text("import sys; sys.exit(1)\n")
    monkeypatch.setattr(
        "scripts.run_aeh_regression._resolve_score_script",
        lambda: fake,
    )
    rc = main(
        [
            "--run-id",
            "r1",
            "--config",
            str(config),
            "--runs-dir",
            str(tmp_path / "reports"),
            "--strict",
        ]
    )
    assert rc == 1
