"""Path helpers for AEH Harbor runs (MLflow / job-dir wiring)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def rewrite_harbor_job_dir(run_result_path: Path) -> str | None:
    """Rewrite absolute ``harbor_job_dir`` to a path relative to a shared ancestor.

    AEH ``log_results._resolve_harbor_job_dir`` rejects absolute paths and
    resolves relative ones against ancestors of the run directory. Harbor
    ``run.py`` currently stores an absolute job dir, which skips trace build.

    **Side effect:** mutates ``run_result.json`` in place (overwrites
    ``harbor_job_dir``). Downstream consumers that need the original absolute
    Harbor path should read it before calling this helper.

    When the job directory is missing (moved/archived), still attempt a
    relative rewrite from the absolute path string so MLflow traces can be
    salvaged.

    Returns the rewritten relative path, or None if unchanged / not possible.
    """
    path = Path(run_result_path)
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text()) or {}
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None

    raw = data.get("harbor_job_dir")
    if not raw:
        return None

    job = Path(str(raw))
    if not job.is_absolute():
        return None
    if not job.is_dir():
        logger.warning(
            "harbor_job_dir does not exist (%s); attempting relative rewrite anyway",
            job,
        )

    run_dir = path.parent.resolve()
    job_resolved = job.resolve() if job.exists() else job
    for root in run_dir.parents:
        try:
            rel = job_resolved.relative_to(root)
        except ValueError:
            continue
        if ".." in rel.parts:
            continue
        rewritten = rel.as_posix()
        data["harbor_job_dir"] = rewritten
        path.write_text(json.dumps(data, indent=2) + "\n")
        logger.info("Rewrote harbor_job_dir -> %s", rewritten)
        return rewritten
    return None
