"""Pluggable observer protocol for evaluation results.

Observers are notified after results are persisted to the database.
They may log to MLflow, push to Langfuse, emit OTel spans, post Slack
notifications, etc.

Observer failures are logged as warnings and never fail the pipeline.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Protocol

from abevalflow.report import AnalysisResult

logger = logging.getLogger(__name__)


class ResultsObserver(Protocol):
    """Interface for downstream result consumers."""

    def on_evaluation_stored(
        self,
        result: AnalysisResult,
        run_id: uuid.UUID,
    ) -> None:
        """Called after a successful DB commit.

        Args:
            result: The validated analysis result that was persisted.
            run_id: The UUID primary key of the stored evaluation run.
        """
        ...


def discover_observers() -> list[ResultsObserver]:
    """Discover and instantiate observers based on environment variables.

    All matching observers are loaded (not first-match). Returns an empty
    list if no observer env vars are configured.
    """
    import os

    observers: list[ResultsObserver] = []

    if os.environ.get("MLFLOW_TRACKING_URI"):
        try:
            from abevalflow.observability.mlflow_observer import MLflowObserver

            prefix = os.environ.get("MLFLOW_EXPERIMENT_PREFIX", "abevalflow")
            observers.append(
                MLflowObserver(
                    tracking_uri=os.environ["MLFLOW_TRACKING_URI"],
                    experiment_prefix=prefix,
                )
            )
            logger.info("MLflow observer enabled (uri=%s)", os.environ["MLFLOW_TRACKING_URI"])
        except ImportError:
            logger.warning("MLflow observer requested but mlflow package not installed — skipping")

    if os.environ.get("LANGFUSE_PUBLIC_KEY"):
        logger.info("Langfuse observer requested but not yet implemented — skipping")

    return observers


def notify_observers(
    observers: list[ResultsObserver],
    result: AnalysisResult,
    run_id: uuid.UUID,
    report_dir: Path | None = None,
    pipeline_run_id: str | None = None,
) -> None:
    """Invoke all observers, catching and logging any errors."""
    kwargs: dict = {}
    if report_dir is not None:
        kwargs["report_dir"] = report_dir
    if pipeline_run_id is not None:
        kwargs["pipeline_run_id"] = pipeline_run_id

    for obs in observers:
        try:
            if kwargs:
                obs.on_evaluation_stored(result, run_id, **kwargs)
            else:
                obs.on_evaluation_stored(result, run_id)
        except TypeError:
            obs.on_evaluation_stored(result, run_id)
        except Exception:
            logger.warning(
                "Observer %s.%s failed",
                type(obs).__module__,
                type(obs).__qualname__,
                exc_info=True,
            )
