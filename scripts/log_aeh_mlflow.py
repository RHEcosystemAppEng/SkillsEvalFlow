"""Log AEH Harbor run results to MLflow (post-evaluate, non-blocking caller).

Requires an importable ``mlflow`` package in the current Python environment
(Tekton evaluate installs ``mlflow-skinny`` + ``pandas`` into ``/tmp`` when
missing). Prefers upstream AEH ``skills/eval-mlflow/scripts/log_results.py``
when present (under ``/opt/agent-eval-harness`` or ``AGENT_EVAL_HARNESS_ROOT``).
Falls back to a minimal metrics/params logger from ``run_result.json`` +
``summary.yaml`` when upstream is absent or no-ops.

Optional actions (same AEH skill tree):
  - ``push-feedback`` — attach judge feedback to traces (``attach_feedback.py``)
  - ``sync-dataset`` — sync cases to the MLflow dataset registry when a schema
    mapping is available or a simple ``input.yaml:prompt`` default applies

Usage::

    python scripts/log_aeh_mlflow.py \\
        --run-id <pipeline-run-id or treatment-<id>> \\
        --config /path/to/eval.yaml \\
        --runs-dir /workspace/source/reports \\
        --tracking-uri http://mlflow.example:5000 \\
        [--actions log-results,push-feedback,sync-dataset]

Skip (exit 0) when ``--enabled false`` or tracking URI is empty.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_AEH_MLFLOW_SCRIPTS = Path("/opt/agent-eval-harness/skills/eval-mlflow/scripts")
_DEFAULT_ACTIONS = ("log-results", "push-feedback", "sync-dataset")
# Upstream log_results.py wording varies; also catch ImportError-style lines.
_MISSING_MLFLOW_MARKERS = (
    "MLflow not installed",
    "mlflow is not installed",
    "No module named 'mlflow'",
    'No module named "mlflow"',
)


def _aeh_script(name: str) -> Path | None:
    root = os.environ.get("AGENT_EVAL_HARNESS_ROOT", "").strip()
    candidates: list[Path] = []
    if root:
        candidates.append(Path(root) / "skills/eval-mlflow/scripts" / name)
    candidates.append(_AEH_MLFLOW_SCRIPTS / name)
    for path in candidates:
        if path.is_file():
            return path
    return None


def _resolve_log_results_script() -> Path | None:
    return _aeh_script("log_results.py")


def _parse_actions(raw: str) -> list[str]:
    actions = [a.strip() for a in (raw or "").split(",") if a.strip()]
    return actions or list(_DEFAULT_ACTIONS)


def _default_schema_mapping(config: Path) -> dict | None:
    """Build a minimal mapping when cases expose ``input.yaml`` with ``prompt``."""
    try:
        raw = yaml.safe_load(config.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    dataset = raw.get("dataset") if isinstance(raw.get("dataset"), dict) else {}
    rel = str(dataset.get("path") or "cases")
    cases_dir = (config.parent / rel).resolve()
    if not cases_dir.is_dir():
        return None
    for case in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        input_yaml = case / "input.yaml"
        if not input_yaml.is_file():
            continue
        try:
            data = yaml.safe_load(input_yaml.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and "prompt" in data:
            mapping: dict = {"inputs": {"prompt": "input.yaml:prompt"}, "expectations": {}}
            # Optional gold files commonly used by AEH samples
            for name in ("reference.md", "reference.yaml"):
                if (case / name).is_file():
                    mapping["expectations"]["reference"] = f"{name}:__file__"
                    break
            return mapping
    return None


def _run_aeh_script(script: Path, argv: list[str], *, runs_dir: Path) -> int:
    env = os.environ.copy()
    env["AGENT_EVAL_RUNS_DIR"] = str(runs_dir)
    cmd = [sys.executable, str(script), *argv]
    logger.info("Running AEH MLflow script: %s", " ".join(cmd))
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def _maybe_sync_dataset(*, config: Path, runs_dir: Path) -> None:
    script = _aeh_script("sync_dataset.py")
    if script is None:
        logger.info("sync_dataset.py not found; skipping sync-dataset")
        return

    mapping_path = config.parent / "schema_mapping.json"
    tmp_path: Path | None = None
    if mapping_path.is_file():
        logger.info("Using schema mapping: %s", mapping_path)
    else:
        mapping = _default_schema_mapping(config)
        if mapping is None:
            logger.info("No schema_mapping.json and no default input.yaml:prompt mapping; skipping sync-dataset")
            return
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, prefix="aeh-schema-mapping-")
        json.dump(mapping, tmp)
        tmp.close()
        tmp_path = Path(tmp.name)
        mapping_path = tmp_path
        logger.info("Using auto-generated schema mapping for sync-dataset")

    try:
        rc = _run_aeh_script(
            script,
            ["--config", str(config), "--mapping", str(mapping_path)],
            runs_dir=runs_dir,
        )
        if rc != 0:
            logger.warning("sync-dataset exited %s (non-blocking)", rc)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _maybe_push_feedback(*, run_id: str, config: Path, runs_dir: Path) -> None:
    script = _aeh_script("attach_feedback.py")
    if script is None:
        logger.info("attach_feedback.py not found; skipping push-feedback")
        return
    rc = _run_aeh_script(
        script,
        [
            "--run-id",
            run_id,
            "--config",
            str(config),
            "--action",
            "push",
            "--source",
            "judge",
        ],
        runs_dir=runs_dir,
    )
    if rc != 0:
        logger.warning("push-feedback exited %s (non-blocking)", rc)


def _mlflow_importable() -> bool:
    try:
        import mlflow  # noqa: F401
    except ImportError:
        return False
    return True


def _upstream_noop_missing_mlflow(combined: str, returncode: int) -> bool:
    """True when upstream log_results likely skipped because mlflow is missing."""
    if any(marker in combined for marker in _MISSING_MLFLOW_MARKERS):
        return True
    # Structural guard: success exit but this interpreter cannot import mlflow.
    if returncode == 0 and not _mlflow_importable():
        return True
    return False


def _run_aeh_log_results(*, script: Path, run_id: str, config: Path, runs_dir: Path) -> int:
    """Run upstream log_results.py.

    Returns 0 on real success. Returns non-zero when the script no-ops because
    ``mlflow`` is missing (upstream often exits 0 with a message — treat as
    failure so we can fall back to the minimal logger).
    """
    env = os.environ.copy()
    env["AGENT_EVAL_RUNS_DIR"] = str(runs_dir)
    cmd = [
        sys.executable,
        str(script),
        "--run-id",
        run_id,
        "--config",
        str(config),
    ]
    logger.info("Running AEH MLflow logger: %s", " ".join(cmd))
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    combined = f"{result.stdout}\n{result.stderr}"
    if _upstream_noop_missing_mlflow(combined, result.returncode):
        logger.warning("AEH log_results.py skipped (mlflow package missing)")
        return 2
    return result.returncode


def _do_log_results(*, run_id: str, config: Path, runs_dir: Path, tracking_uri: str) -> int:
    """Log results via AEH script or minimal fallback. Returns 0 on success."""
    script = _resolve_log_results_script()
    if script is not None:
        rc = _run_aeh_log_results(
            script=script,
            run_id=run_id,
            config=config,
            runs_dir=runs_dir,
        )
        if rc == 0:
            return 0
        logger.warning("AEH log_results.py exited %s; trying minimal logger", rc)

    try:
        _minimal_mlflow_log(
            run_id=run_id,
            config=config,
            runs_dir=runs_dir,
            tracking_uri=tracking_uri,
        )
    except Exception:
        logger.exception("MLflow logging failed")
        return 1
    return 0


def _resolve_run_dir(runs_dir: Path, skill: str, run_id: str) -> Path:
    """Locate ``runs_dir/<skill>/<run_id>``, with pairwise prefix fallbacks.

    Pairwise AEH layouts use ``control-<id>`` / ``treatment-<id>``. When callers
    pass a bare pipeline-run id, prefer the treatment dir, then control.
    """
    candidates = [runs_dir / skill / run_id]
    if not run_id.startswith(("control-", "treatment-")):
        candidates.append(runs_dir / skill / f"treatment-{run_id}")
        candidates.append(runs_dir / skill / f"control-{run_id}")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    tried = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"AEH run dir not found for skill={skill!r} run_id={run_id!r}; tried: {tried}")


def _minimal_mlflow_log(*, run_id: str, config: Path, runs_dir: Path, tracking_uri: str) -> None:
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError("mlflow is not installed; pip install 'mlflow[genai]' or use AEH image with mlflow") from exc

    raw = yaml.safe_load(config.read_text()) or {}
    skill = str(raw.get("skill") or config.parent.name)
    mlflow_cfg = raw.get("mlflow") if isinstance(raw.get("mlflow"), dict) else {}
    experiment = str(mlflow_cfg.get("experiment") or skill or "abevalflow-aeh")

    run_dir = _resolve_run_dir(runs_dir, skill, run_id)

    run_result: dict = {}
    rr_path = run_dir / "run_result.json"
    if rr_path.is_file():
        run_result = json.loads(rr_path.read_text()) or {}

    summary: dict = {}
    summary_path = run_dir / "summary.yaml"
    if summary_path.is_file():
        loaded = yaml.safe_load(summary_path.read_text()) or {}
        if isinstance(loaded, dict):
            summary = loaded

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=run_id):
        mlflow.log_param("skill", skill)
        mlflow.log_param("run_id", run_id)
        mlflow.log_param("execution_mode", run_result.get("execution_mode", "harbor"))
        if run_result.get("model"):
            mlflow.log_param("model", run_result["model"])

        tokens = run_result.get("token_usage") or {}
        if isinstance(tokens, dict):
            for key in ("input", "output", "prompt", "completion", "total"):
                if key in tokens and tokens[key] is not None:
                    mlflow.log_metric(f"tokens_{key}", float(tokens[key]))
            # Harbor-style nested usage
            for key in ("input_tokens", "output_tokens", "cache_read", "cache_create"):
                if key in tokens and tokens[key] is not None:
                    mlflow.log_metric(f"tokens_{key}", float(tokens[key]))

        if run_result.get("cost_usd") is not None:
            mlflow.log_metric("cost_usd", float(run_result["cost_usd"]))
        if run_result.get("mean_reward") is not None:
            mlflow.log_metric("mean_reward", float(run_result["mean_reward"]))
        elif summary.get("mean_reward") is not None:
            mlflow.log_metric("mean_reward", float(summary["mean_reward"]))

        for artifact in (summary_path, rr_path, run_dir / "report.html"):
            if not artifact.is_file():
                continue
            try:
                mlflow.log_artifact(str(artifact))
            except Exception:
                # Metrics/params already recorded; artifacts need a proxied
                # artifact root (mlflow-artifacts:/) on the tracking server.
                logger.warning("MLflow artifact upload failed for %s", artifact, exc_info=True)

    logger.info("Minimal MLflow log complete: experiment=%s run_id=%s", experiment, run_id)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Log AEH results to MLflow")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", ""))
    parser.add_argument(
        "--enabled",
        default="true",
        help="Set to false/0/no to skip (default: true when URI set by caller)",
    )
    parser.add_argument(
        "--actions",
        default=",".join(_DEFAULT_ACTIONS),
        help=(
            f"Comma-separated actions: log-results, push-feedback, sync-dataset (default: {','.join(_DEFAULT_ACTIONS)})"
        ),
    )
    args = parser.parse_args(argv)

    enabled = str(args.enabled).strip().lower() in {"1", "true", "yes", "on"}
    tracking_uri = (args.tracking_uri or "").strip()
    if not enabled:
        logger.info("MLflow logging disabled (--enabled=%s)", args.enabled)
        return 0
    if not tracking_uri:
        logger.info("MLflow logging skipped (empty tracking URI)")
        return 0

    os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
    config = args.config.resolve()
    runs_dir = args.runs_dir.resolve()
    if not config.is_file():
        logger.error("Config not found: %s", config)
        return 1

    if not _mlflow_importable():
        logger.error(
            "Python package 'mlflow' is not installed in this environment; install with: python -m pip install mlflow"
        )
        return 1

    actions = _parse_actions(args.actions)
    logger.info("MLflow actions: %s", ", ".join(actions))

    # Belt-and-suspenders: AEH log_results rejects absolute harbor_job_dir.
    try:
        from abevalflow.harbor_extensions.aeh_paths import rewrite_harbor_job_dir

        raw_cfg = yaml.safe_load(config.read_text()) or {}
        skill = str(raw_cfg.get("skill") or config.parent.name)
        rr = runs_dir / skill / args.run_id / "run_result.json"
        if rr.is_file():
            rewritten = rewrite_harbor_job_dir(rr)
            if rewritten:
                logger.info("Rewrote harbor_job_dir -> %s", rewritten)
    except Exception:
        logger.warning("harbor_job_dir rewrite failed; continuing", exc_info=True)

    # sync-dataset is run-independent; do it first so the registry is warm.
    if "sync-dataset" in actions:
        try:
            _maybe_sync_dataset(config=config, runs_dir=runs_dir)
        except Exception:
            logger.warning("sync-dataset failed (non-blocking)", exc_info=True)

    log_rc = 0
    if "log-results" in actions:
        log_rc = _do_log_results(
            run_id=args.run_id,
            config=config,
            runs_dir=runs_dir,
            tracking_uri=tracking_uri,
        )

    if "push-feedback" in actions:
        try:
            _maybe_push_feedback(run_id=args.run_id, config=config, runs_dir=runs_dir)
        except Exception:
            logger.warning("push-feedback failed (non-blocking)", exc_info=True)

    # Keep historical behavior: non-zero only when log-results itself fails.
    return log_rc


if __name__ == "__main__":
    raise SystemExit(main())
