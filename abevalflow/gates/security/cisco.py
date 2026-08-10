"""Cisco security scanner gate."""

from __future__ import annotations

from pathlib import Path

from abevalflow.gates.base import GateResult
from abevalflow.gates.security import register_security_gate
from abevalflow.gates.security.base import SecurityGate
from abevalflow.observability.decorators import timed_gate
from abevalflow.schemas import GatePolicy


@register_security_gate("cisco")
class CiscoGate(SecurityGate):
    """Cisco AI Skill Scanner security gate.

    Reads security-scan.json produced by the test phase's security scan step.
    Pass/fail depends on mode:
    - warn: always passes (findings are advisory)
    - block: fails if HIGH or CRITICAL findings exist
    """

    name = "cisco"
    scan_filename = "security-scan.json"

    @timed_gate
    def evaluate(
        self,
        reports_dir: Path,
        policy: GatePolicy,
    ) -> GateResult:
        """Evaluate Cisco security scan results."""
        return self.evaluate_scan_json(reports_dir, policy)
