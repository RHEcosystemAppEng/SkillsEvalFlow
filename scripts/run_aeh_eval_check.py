#!/usr/bin/env python3
"""Run AEH harness inventory (eval-check Step 1) in advisory mode.

The full ``/eval-check`` skill also does LLM cross-component analysis; in Tekton
we only run the deterministic ``harness_inventory.py`` scanner and write a
report artifact. Always exits 0 unless ``--strict`` is set.

Usage::

    python scripts/run_aeh_eval_check.py \\
        --root /workspace/source/submissions/my-skill \\
        --output /workspace/source/reports/my-skill/harness-inventory.yaml
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_INVENTORY_CANDIDATES = (Path("/opt/agent-eval-harness/skills/eval-check/scripts/harness_inventory.py"),)


def _resolve_inventory_script() -> Path | None:
    root = os.environ.get("AGENT_EVAL_HARNESS_ROOT", "").strip()
    candidates: list[Path] = []
    if root:
        candidates.append(Path(root) / "skills/eval-check/scripts/harness_inventory.py")
    candidates.extend(_INVENTORY_CANDIDATES)
    for path in candidates:
        if path.is_file():
            return path
    return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Submission / project root to scan (skills/, CLAUDE.md, …)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write inventory YAML (default: stdout only)",
    )
    parser.add_argument(
        "--enabled",
        default="true",
        help="Set false/0/no to skip (default: true)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if the inventory script fails (default: advisory)",
    )
    args = parser.parse_args(argv)

    enabled = str(args.enabled).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("AEH eval-check disabled (--enabled=%s)", args.enabled)
        return 0

    root = args.root.resolve()
    if not root.is_dir():
        logger.warning("Eval-check root not found: %s — skipping", root)
        return 0

    script = _resolve_inventory_script()
    if script is None:
        logger.warning("AEH harness_inventory.py not found (set AGENT_EVAL_HARNESS_ROOT or use AEH image); skipping")
        return 0

    cmd = [sys.executable, str(script), "--root", str(root), "--format", "yaml"]
    # Older inventory scripts may not support --format; fall back to text.
    logger.info("Running AEH harness inventory (advisory): %s", " ".join(cmd))
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0 and "unrecognized arguments" in (result.stderr or ""):
        cmd = [sys.executable, str(script), "--root", str(root)]
        logger.info("Retrying without --format: %s", " ".join(cmd))
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    combined = (result.stdout or "") + (result.stderr or "")
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# AEH harness inventory (advisory — inventory only; "
            "full /eval-check LLM analysis is interactive)\n"
            f"# root={root}\n"
            f"# exit_code={result.returncode}\n\n"
        )
        args.output.write_text(header + combined)
        logger.info("Wrote inventory report: %s", args.output)

    if result.returncode != 0:
        logger.warning(
            "AEH harness inventory exited %s — advisory, not failing the step",
            result.returncode,
        )
        return result.returncode if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
