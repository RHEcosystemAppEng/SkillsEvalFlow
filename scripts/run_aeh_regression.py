#!/usr/bin/env python3
"""Run AEH ``score.py regression`` in advisory (non-blocking) mode.

Loads an already-scored AEH run's ``summary.yaml`` and compares judge
aggregates to ``thresholds:`` in ``eval.yaml``. Optionally compares against
a prior run via ``--baseline``.

Always exits 0 unless ``--strict`` is set, so Tekton can surface the check
without failing the PipelineRun.

Usage::

    python scripts/run_aeh_regression.py \\
        --run-id <id> \\
        --config /path/to/eval.yaml \\
        --runs-dir /workspace/source/reports \\
        [--baseline <prior-run-id>] \\
        [--output /path/to/aeh-regression.txt]
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_SCORE_CANDIDATES = (
    Path("/opt/agent-eval-harness/skills/eval-run/scripts/score.py"),
)


def _resolve_score_script() -> Path | None:
    root = os.environ.get("AGENT_EVAL_HARNESS_ROOT", "").strip()
    candidates: list[Path] = []
    if root:
        candidates.append(Path(root) / "skills/eval-run/scripts/score.py")
    candidates.extend(_SCORE_CANDIDATES)
    for path in candidates:
        if path.is_file():
            return path
    return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument(
        "--baseline",
        default="",
        help="Optional prior AEH run-id under the same eval for relative drift check",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the regression report text",
    )
    parser.add_argument(
        "--enabled",
        default="true",
        help="Set false/0/no to skip (default: true)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when AEH reports regressions (default: advisory)",
    )
    args = parser.parse_args(argv)

    enabled = str(args.enabled).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("AEH regression check disabled (--enabled=%s)", args.enabled)
        return 0

    config = args.config.resolve()
    runs_dir = args.runs_dir.resolve()
    if not config.is_file():
        logger.error("Config not found: %s", config)
        return 0 if not args.strict else 1

    script = _resolve_score_script()
    if script is None:
        logger.warning(
            "AEH score.py not found (set AGENT_EVAL_HARNESS_ROOT or use AEH image); skipping"
        )
        return 0

    env = os.environ.copy()
    env["AGENT_EVAL_RUNS_DIR"] = str(runs_dir)
    cmd = [
        sys.executable,
        str(script),
        "regression",
        "--run-id",
        args.run_id,
        "--config",
        str(config),
    ]
    baseline = (args.baseline or "").strip()
    if baseline:
        cmd.extend(["--baseline", baseline])

    logger.info("Running AEH regression (advisory): %s", " ".join(cmd))
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    combined = (result.stdout or "") + (result.stderr or "")
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# AEH regression (advisory)\n"
            f"# run_id={args.run_id}\n"
            f"# baseline={baseline or '(none)'}\n"
            f"# exit_code={result.returncode}\n\n"
        )
        args.output.write_text(header + combined)

    if result.returncode == 0:
        logger.info("AEH regression: REGRESSIONS: 0 (advisory)")
        return 0

    logger.warning(
        "AEH regression reported issues (exit %s) — advisory, not failing the step",
        result.returncode,
    )
    return result.returncode if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
