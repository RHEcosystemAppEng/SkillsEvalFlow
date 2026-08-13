#!/usr/bin/env python3
"""Append LLM semantic security findings into an existing scan JSON file.

Called after harness-eval's deterministic scan to add LLM-detected
findings (anti-jailbreak, semantic attacks, description-behavior mismatch)
into the same security JSON the gate reads.

Usage:
    python scripts/llm_security_review.py <submission_dir> --scan-json <path>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM semantic security review")
    parser.add_argument("submission_dir", type=Path)
    parser.add_argument(
        "--scan-json",
        type=Path,
        required=True,
        help="Path to existing security scan JSON (findings will be appended)",
    )
    args = parser.parse_args()

    if not args.submission_dir.is_dir():
        logger.error("Not a directory: %s", args.submission_dir)
        return 1

    from abevalflow.security.llm_review import llm_security_review

    llm_findings = llm_security_review(args.submission_dir)
    if not llm_findings:
        logger.info("LLM review: no findings")
        return 0

    logger.info("LLM review: %d findings", len(llm_findings))

    scan_data: dict = {"findings": []}
    if args.scan_json.exists():
        try:
            scan_data = json.loads(args.scan_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read existing scan JSON: %s", e)

    scan_data.setdefault("findings", []).extend(llm_findings)

    args.scan_json.write_text(
        json.dumps(scan_data, indent=2),
        encoding="utf-8",
    )
    logger.info("Appended %d LLM findings to %s", len(llm_findings), args.scan_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
