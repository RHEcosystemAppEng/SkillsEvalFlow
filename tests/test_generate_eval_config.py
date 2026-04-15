"""Tests for scripts/generate_eval_config.py — Harbor eval config generation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.generate_eval_config import (
    build_eval_config,
    generate_eval_config,
    load_metadata,
    main,
)


@pytest.fixture()
def minimal_submission(tmp_path: Path) -> Path:
    """Submission with only a name — all defaults."""
    sub = tmp_path / "my-submission"
    sub.mkdir()
    (sub / "metadata.yaml").write_text(yaml.dump({"name": "my-submission"}))
    return sub


@pytest.fixture()
def custom_submission(tmp_path: Path) -> Path:
    """Submission with custom experiment and resource config."""
    sub = tmp_path / "custom-eval"
    sub.mkdir()
    meta = {
        "name": "custom-eval",
        "description": "A custom evaluation",
        "experiment": {"n_trials": 10, "type": "model"},
        "agent_timeout_sec": 1200.0,
        "verifier_timeout_sec": 240.0,
        "agent_setup_timeout_sec": 300.0,
        "build_timeout_sec": 900.0,
        "cpus": 2,
        "memory_mb": 4096,
        "storage_mb": 20480,
    }
    (sub / "metadata.yaml").write_text(yaml.dump(meta))
    return sub


TREATMENT_DIR = "/workspace/tasks-treatment/my-submission"
CONTROL_DIR = "/workspace/tasks-control/my-submission"
TREATMENT_REF = "registry.example.com/ns/my-submission@sha256:aaa111"
CONTROL_REF = "registry.example.com/ns/my-submission@sha256:bbb222"


class TestLoadMetadata:
    def test_loads_minimal(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        assert meta.name == "my-submission"
        assert meta.experiment.n_trials == 20

    def test_loads_custom(self, custom_submission: Path):
        meta = load_metadata(custom_submission)
        assert meta.name == "custom-eval"
        assert meta.experiment.n_trials == 10
        assert meta.cpus == 2

    def test_missing_metadata_raises(self, tmp_path: Path):
        sub = tmp_path / "empty"
        sub.mkdir()
        with pytest.raises(FileNotFoundError):
            load_metadata(sub)


class TestBuildEvalConfigPrebuilt:
    def test_basic_structure(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR,
            eval_mode="prebuilt",
            treatment_image_ref=TREATMENT_REF,
            control_image_ref=CONTROL_REF,
        )
        assert config["job_name"] == "my-submission-eval"
        assert config["n_attempts"] == 20
        assert config["environment"]["type"] == "openshift"
        assert config["environment"]["delete"] is True
        assert len(config["tasks"]) == 2

    def test_treatment_task_has_image_ref(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR,
            eval_mode="prebuilt",
            treatment_image_ref=TREATMENT_REF,
            control_image_ref=CONTROL_REF,
        )
        treatment = config["tasks"][0]
        assert treatment["path"] == TREATMENT_DIR
        assert treatment["environment_kwargs"]["image_ref"] == TREATMENT_REF

    def test_control_task_has_image_ref(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR,
            eval_mode="prebuilt",
            treatment_image_ref=TREATMENT_REF,
            control_image_ref=CONTROL_REF,
        )
        control = config["tasks"][1]
        assert control["path"] == CONTROL_DIR
        assert control["environment_kwargs"]["image_ref"] == CONTROL_REF

    def test_no_force_build(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR,
            eval_mode="prebuilt",
            treatment_image_ref=TREATMENT_REF,
            control_image_ref=CONTROL_REF,
        )
        assert "force_build" not in config["environment"]


class TestBuildEvalConfigLocalBuild:
    def test_no_environment_kwargs(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR, eval_mode="local-build",
        )
        assert "environment_kwargs" not in config["tasks"][0]
        assert "environment_kwargs" not in config["tasks"][1]

    def test_force_build_enabled(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR, eval_mode="local-build",
        )
        assert config["environment"]["force_build"] is True

    def test_task_paths_set(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR, eval_mode="local-build",
        )
        assert config["tasks"][0]["path"] == TREATMENT_DIR
        assert config["tasks"][1]["path"] == CONTROL_DIR


class TestCustomMetadataFields:
    def test_n_trials_from_metadata(self, custom_submission: Path):
        meta = load_metadata(custom_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR, eval_mode="local-build",
        )
        assert config["n_attempts"] == 10

    def test_resource_overrides(self, custom_submission: Path):
        meta = load_metadata(custom_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR, eval_mode="local-build",
        )
        assert config["environment"]["override_cpus"] == 2
        assert config["environment"]["override_memory_mb"] == 4096
        assert config["environment"]["override_storage_mb"] == 20480

    def test_timeout_multipliers(self, custom_submission: Path):
        meta = load_metadata(custom_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR, eval_mode="local-build",
        )
        assert config["agent_timeout_multiplier"] == pytest.approx(2.0)
        assert config["verifier_timeout_multiplier"] == pytest.approx(2.0)
        assert config["agent_setup_timeout_multiplier"] == pytest.approx(0.5)
        assert config["environment_build_timeout_multiplier"] == pytest.approx(1.5)

    def test_default_timeouts_produce_1x_multiplier(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR, eval_mode="local-build",
        )
        assert config["agent_timeout_multiplier"] == pytest.approx(1.0)
        assert config["verifier_timeout_multiplier"] == pytest.approx(1.0)
        assert config["agent_setup_timeout_multiplier"] == pytest.approx(1.0)
        assert config["environment_build_timeout_multiplier"] == pytest.approx(1.0)

    def test_custom_jobs_dir(self, minimal_submission: Path):
        meta = load_metadata(minimal_submission)
        config = build_eval_config(
            meta, TREATMENT_DIR, CONTROL_DIR,
            eval_mode="local-build", jobs_dir="/workspace/results",
        )
        assert config["jobs_dir"] == "/workspace/results"


class TestGenerateEvalConfig:
    def test_writes_yaml_file(self, minimal_submission: Path, tmp_path: Path):
        output = tmp_path / "config.yaml"
        config = generate_eval_config(
            submission_dir=minimal_submission,
            treatment_task_dir=TREATMENT_DIR,
            control_task_dir=CONTROL_DIR,
            output=output,
            eval_mode="prebuilt",
            treatment_image_ref=TREATMENT_REF,
            control_image_ref=CONTROL_REF,
        )
        assert output.is_file()
        loaded = yaml.safe_load(output.read_text())
        assert loaded["job_name"] == config["job_name"]
        assert loaded["n_attempts"] == config["n_attempts"]
        assert len(loaded["tasks"]) == 2

    def test_creates_parent_dirs(self, minimal_submission: Path, tmp_path: Path):
        output = tmp_path / "nested" / "dir" / "config.yaml"
        generate_eval_config(
            submission_dir=minimal_submission,
            treatment_task_dir=TREATMENT_DIR,
            control_task_dir=CONTROL_DIR,
            output=output,
            eval_mode="local-build",
        )
        assert output.is_file()


class TestMainCLI:
    def test_prebuilt_mode(self, minimal_submission: Path, tmp_path: Path):
        output = tmp_path / "out.yaml"
        rc = main([
            "--submission-dir", str(minimal_submission),
            "--treatment-task-dir", TREATMENT_DIR,
            "--control-task-dir", CONTROL_DIR,
            "--output", str(output),
            "--eval-mode", "prebuilt",
            "--treatment-image-ref", TREATMENT_REF,
            "--control-image-ref", CONTROL_REF,
        ])
        assert rc == 0
        loaded = yaml.safe_load(output.read_text())
        assert loaded["tasks"][0]["environment_kwargs"]["image_ref"] == TREATMENT_REF

    def test_local_build_mode(self, minimal_submission: Path, tmp_path: Path):
        output = tmp_path / "out.yaml"
        rc = main([
            "--submission-dir", str(minimal_submission),
            "--treatment-task-dir", TREATMENT_DIR,
            "--control-task-dir", CONTROL_DIR,
            "--output", str(output),
            "--eval-mode", "local-build",
        ])
        assert rc == 0
        loaded = yaml.safe_load(output.read_text())
        assert "environment_kwargs" not in loaded["tasks"][0]

    def test_prebuilt_missing_refs_exits_error(
        self, minimal_submission: Path, tmp_path: Path,
    ):
        output = tmp_path / "out.yaml"
        with pytest.raises(SystemExit) as exc_info:
            main([
                "--submission-dir", str(minimal_submission),
                "--treatment-task-dir", TREATMENT_DIR,
                "--control-task-dir", CONTROL_DIR,
                "--output", str(output),
                "--eval-mode", "prebuilt",
            ])
        assert exc_info.value.code == 2

    def test_nonexistent_submission_dir(self, tmp_path: Path):
        output = tmp_path / "out.yaml"
        rc = main([
            "--submission-dir", str(tmp_path / "no-such-dir"),
            "--treatment-task-dir", TREATMENT_DIR,
            "--control-task-dir", CONTROL_DIR,
            "--output", str(output),
            "--eval-mode", "local-build",
        ])
        assert rc == 1
