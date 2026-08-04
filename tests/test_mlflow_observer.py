"""Tests for abevalflow.observability.mlflow_observer."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from abevalflow.observability.mlflow_observer import MLflowObserver
from abevalflow.report import (
    AnalysisResult,
    AnalysisSummary,
    Provenance,
    Recommendation,
    TrialResult,
    VariantSummary,
)


def _sample_result(name: str = "test-skill") -> AnalysisResult:
    return AnalysisResult(
        submission_name=name,
        provenance=Provenance(
            commit_sha="abc123",
            pipeline_run_id="tekton-run-001",
            eval_engine="harbor",
        ),
        summary=AnalysisSummary(
            treatment=VariantSummary(
                n_trials=20,
                n_passed=16,
                n_failed=3,
                n_errors=1,
                pass_rate=0.8,
                mean_reward=0.72,
            ),
            control=VariantSummary(
                n_trials=20,
                n_passed=10,
                n_failed=8,
                n_errors=2,
                pass_rate=0.5,
                mean_reward=0.45,
            ),
            uplift=0.3,
            mean_reward_gap=0.27,
            ttest_p_value=0.02,
            fisher_p_value=0.04,
            recommendation=Recommendation.PASS,
        ),
        trials={
            "treatment": [TrialResult(trial_name=f"t-{i}", reward=0.7) for i in range(3)],
            "control": [TrialResult(trial_name=f"c-{i}", reward=0.4) for i in range(3)],
        },
    )


class TestMLflowObserver:
    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_creates_experiment_and_logs_run(self, mock_mlflow: MagicMock) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-123"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4())

        mock_mlflow.set_tracking_uri.assert_called_once_with("http://mlflow:5000")
        mock_mlflow.create_experiment.assert_called_once_with("abevalflow/test-skill")
        mock_mlflow.log_params.assert_called_once()
        mock_mlflow.log_metrics.assert_called_once()

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_uses_existing_experiment(self, mock_mlflow: MagicMock) -> None:
        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "existing-exp"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4())

        mock_mlflow.create_experiment.assert_not_called()
        mock_mlflow.start_run.assert_called_once_with(experiment_id="existing-exp", run_name="tekton-run-001")

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_logs_correct_metrics(self, mock_mlflow: MagicMock) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-1"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4())

        metrics = mock_mlflow.log_metrics.call_args[0][0]
        assert metrics["uplift"] == 0.3
        assert metrics["treatment_pass_rate"] == 0.8
        assert metrics["control_pass_rate"] == 0.5

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_logs_tags(self, mock_mlflow: MagicMock) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-1"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4())

        tags = mock_mlflow.set_tags.call_args[0][0]
        assert tags["recommendation"] == "pass"
        assert tags["eval_engine"] == "harbor"
        assert tags["submission_name"] == "test-skill"

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_logs_artifacts_from_report_dir(self, mock_mlflow: MagicMock, tmp_path: Path) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-1"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        (tmp_path / "scorecard.json").write_text('{"recommendation": "pass", "gates": []}')
        (tmp_path / "report.md").write_text("# Report")

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4(), report_dir=tmp_path)

        assert mock_mlflow.log_artifact.call_count == 2

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_logs_scorecard_gate_scores(self, mock_mlflow: MagicMock, tmp_path: Path) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-1"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        scorecard = {
            "recommendation": "pass",
            "highest_certification": "trusted",
            "gates_passed": 2,
            "gates_failed": 0,
            "gates": [
                {"gate_name": "evaluation", "policy_key": "harbor", "score": 0.85, "findings_count": 0},
                {"gate_name": "security", "policy_key": "cisco", "score": 1.0, "findings_count": 2},
            ],
        }
        (tmp_path / "scorecard.json").write_text(json.dumps(scorecard))

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4(), report_dir=tmp_path)

        mock_mlflow.log_metric.assert_any_call("gates_passed", 2)
        mock_mlflow.log_metric.assert_any_call("gates_failed", 0)
        mock_mlflow.log_metric.assert_any_call("gate_score_harbor", 0.85)
        mock_mlflow.log_metric.assert_any_call("gate_score_cisco", 1.0)
        mock_mlflow.log_metric.assert_any_call("gate_findings_cisco", 2)
        mock_mlflow.set_tag.assert_any_call("highest_certification", "trusted")

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_logs_token_metrics_from_checkpoint(self, mock_mlflow: MagicMock, tmp_path: Path) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-1"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        checkpoint = {
            "token_usage": {
                "quality_review": {
                    "prompt_tokens": 500,
                    "completion_tokens": 200,
                    "call_count": 1,
                }
            },
            "model_name": "claude-sonnet",
        }
        (tmp_path / "_metrics_checkpoint.json").write_text(json.dumps(checkpoint))

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4(), report_dir=tmp_path)

        token_metrics = mock_mlflow.log_metrics.call_args_list[-1][0][0]
        assert token_metrics["total_prompt_tokens"] == 500
        assert token_metrics["total_completion_tokens"] == 200
        assert token_metrics["total_tokens"] == 700
        assert token_metrics["llm_calls_count"] == 1
        mock_mlflow.set_tag.assert_any_call("model_name", "claude-sonnet")

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_custom_experiment_prefix(self, mock_mlflow: MagicMock) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-1"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        observer = MLflowObserver(tracking_uri="http://mlflow:5000", experiment_prefix="custom")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4())

        mock_mlflow.create_experiment.assert_called_once_with("custom/test-skill")

    @patch("abevalflow.observability.mlflow_observer.mlflow")
    def test_no_report_dir_skips_artifacts(self, mock_mlflow: MagicMock) -> None:
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-1"
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        observer = MLflowObserver(tracking_uri="http://mlflow:5000")
        observer.on_evaluation_stored(_sample_result(), uuid.uuid4())

        mock_mlflow.log_artifact.assert_not_called()


class TestDiscoverObservers:
    def test_no_env_returns_empty(self, monkeypatch) -> None:
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        from abevalflow.db.observer import discover_observers

        assert discover_observers() == []

    @patch("abevalflow.observability.mlflow_observer.MLflowObserver")
    def test_mlflow_uri_creates_observer(self, mock_cls: MagicMock, monkeypatch) -> None:
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
        from abevalflow.db.observer import discover_observers

        observers = discover_observers()
        assert len(observers) == 1
