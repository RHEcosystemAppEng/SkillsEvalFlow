"""Security scan a submission directory for security issues.

Wraps abevalflow.security.skillmd_scanner.scan_directory to produce JSON
output compatible with the gate evaluation pipeline.

Exit codes: 0 = pass (no high/critical findings), 1 = blocked.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from abevalflow.security.skillmd_scanner import scan_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Security scan a submission directory"
    )
    parser.add_argument(
        "submission_dir", type=Path, help="Path to the submission directory"
    )
    args = parser.parse_args(argv)

    submission_dir: Path = args.submission_dir
    if not submission_dir.is_dir():
        result = {
            "passed": False,
            "findings": [],
            "summary": f"Not a directory: {submission_dir}",
        }
        print(json.dumps(result, indent=2))
        return 1

    scan_result = scan_directory(submission_dir)
    findings = scan_result["findings"]
    blocking = [f for f in findings if f.get("severity") in ("critical", "high")]
    passed = len(blocking) == 0

    output = {
        "passed": passed,
        "findings": findings,
        "summary": f"{len(blocking)} blocking finding(s), {len(findings)} total in {submission_dir.name}",
    }
    print(json.dumps(output, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
