"""Generate a Harbor job config YAML for A/B evaluation.

Reads metadata.yaml from the submission directory and produces a config
file that can be passed to ``harbor run -c <config.yaml>``.

Usage:
    python scripts/generate_eval_config.py \
        --submission-dir /workspace/submissions/my-submission \
        --treatment-task-dir /workspace/tasks-treatment/my-submission \
        --control-task-dir /workspace/tasks-control/my-submission \
        --eval-mode prebuilt \
        --treatment-image-ref registry/ns/img@sha256:abc \
        --control-image-ref registry/ns/img@sha256:def \
        --output /tmp/eval-config.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from abevalflow.schemas import SubmissionMetadata

logger = logging.getLogger(__name__)

EVAL_MODES = ("prebuilt", "local-build")

# Harbor's default agent/verifier/setup timeouts used as reference baselines
# for computing timeout multipliers from the absolute seconds in metadata.yaml.
_HARBOR_DEFAULT_AGENT_TIMEOUT = 600.0
_HARBOR_DEFAULT_VERIFIER_TIMEOUT = 120.0
_HARBOR_DEFAULT_SETUP_TIMEOUT = 600.0
_HARBOR_DEFAULT_BUILD_TIMEOUT = 600.0


def load_metadata(submission_dir: Path) -> SubmissionMetadata:
    """Load and validate metadata.yaml from a submission directory."""
    meta_path = submission_dir / "metadata.yaml"
    with meta_path.open() as f:
        raw = yaml.safe_load(f)
    return SubmissionMetadata(**raw)


def _timeout_multiplier(actual: float, default: float) -> float:
    """Compute a timeout multiplier relative to Harbor's default.

    Returns 1.0 when actual equals the default, >1.0 for longer timeouts.
    """
    if default <= 0:
        return 1.0
    return actual / default


def build_eval_config(
    metadata: SubmissionMetadata,
    treatment_task_dir: str,
    control_task_dir: str,
    eval_mode: str,
    jobs_dir: str = "jobs",
    treatment_image_ref: str = "",
    control_image_ref: str = "",
) -> dict[str, Any]:
    """Build a dict matching Harbor's JobConfig schema."""
    treatment_task: dict[str, Any] = {"path": treatment_task_dir}
    control_task: dict[str, Any] = {"path": control_task_dir}

    if eval_mode == "prebuilt":
        treatment_task["environment_kwargs"] = {"image_ref": treatment_image_ref}
        control_task["environment_kwargs"] = {"image_ref": control_image_ref}

    agent_mult = _timeout_multiplier(
        metadata.agent_timeout_sec, _HARBOR_DEFAULT_AGENT_TIMEOUT
    )
    verifier_mult = _timeout_multiplier(
        metadata.verifier_timeout_sec, _HARBOR_DEFAULT_VERIFIER_TIMEOUT
    )
    setup_mult = _timeout_multiplier(
        metadata.agent_setup_timeout_sec, _HARBOR_DEFAULT_SETUP_TIMEOUT
    )
    build_mult = _timeout_multiplier(
        metadata.build_timeout_sec, _HARBOR_DEFAULT_BUILD_TIMEOUT
    )

    config: dict[str, Any] = {
        "job_name": f"{metadata.name}-eval",
        "jobs_dir": jobs_dir,
        "n_attempts": metadata.experiment.n_trials,
        "timeout_multiplier": 1.0,
        "agent_timeout_multiplier": agent_mult,
        "verifier_timeout_multiplier": verifier_mult,
        "agent_setup_timeout_multiplier": setup_mult,
        "environment_build_timeout_multiplier": build_mult,
        "n_concurrent_trials": 4,
        "environment": {
            "type": "openshift",
            "delete": True,
            "override_cpus": metadata.cpus,
            "override_memory_mb": metadata.memory_mb,
            "override_storage_mb": metadata.storage_mb,
        },
        "agents": [{}],
        "tasks": [treatment_task, control_task],
    }

    if eval_mode == "local-build":
        config["environment"]["force_build"] = True

    return config


def generate_eval_config(
    submission_dir: Path,
    treatment_task_dir: str,
    control_task_dir: str,
    output: Path,
    eval_mode: str,
    treatment_image_ref: str = "",
    control_image_ref: str = "",
    jobs_dir: str = "jobs",
) -> dict[str, Any]:
    """End-to-end: load metadata, build config, write YAML, return the dict."""
    metadata = load_metadata(submission_dir)
    config = build_eval_config(
        metadata=metadata,
        treatment_task_dir=treatment_task_dir,
        control_task_dir=control_task_dir,
        eval_mode=eval_mode,
        jobs_dir=jobs_dir,
        treatment_image_ref=treatment_image_ref,
        control_image_ref=control_image_ref,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    logger.info("Wrote eval config to %s", output)
    return config


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Generate a Harbor eval config from submission metadata",
    )
    parser.add_argument(
        "--submission-dir",
        type=Path,
        required=True,
        help="Path to the submission directory containing metadata.yaml",
    )
    parser.add_argument(
        "--treatment-task-dir",
        required=True,
        help="Path to the scaffolded treatment task directory",
    )
    parser.add_argument(
        "--control-task-dir",
        required=True,
        help="Path to the scaffolded control task directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the generated config YAML",
    )
    parser.add_argument(
        "--eval-mode",
        choices=EVAL_MODES,
        required=True,
        help="'prebuilt' uses digest image refs; 'local-build' lets Harbor build from Dockerfiles",
    )
    parser.add_argument(
        "--treatment-image-ref",
        default="",
        help="Digest-based image ref for treatment variant (required for prebuilt mode)",
    )
    parser.add_argument(
        "--control-image-ref",
        default="",
        help="Digest-based image ref for control variant (required for prebuilt mode)",
    )
    parser.add_argument(
        "--jobs-dir",
        default="jobs",
        help="Directory where Harbor writes job results (default: jobs)",
    )

    args = parser.parse_args(argv)

    if args.eval_mode == "prebuilt":
        if not args.treatment_image_ref or not args.control_image_ref:
            parser.error(
                "--treatment-image-ref and --control-image-ref are required "
                "when --eval-mode is 'prebuilt'"
            )

    if not args.submission_dir.is_dir():
        logger.error("Submission directory does not exist: %s", args.submission_dir)
        return 1

    generate_eval_config(
        submission_dir=args.submission_dir,
        treatment_task_dir=args.treatment_task_dir,
        control_task_dir=args.control_task_dir,
        output=args.output,
        eval_mode=args.eval_mode,
        treatment_image_ref=args.treatment_image_ref,
        control_image_ref=args.control_image_ref,
        jobs_dir=args.jobs_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
