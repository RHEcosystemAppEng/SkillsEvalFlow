# Extensibility

## Adding a New Engine

1. Create a new file in `abevalflow/engines/`:

```python
# abevalflow/engines/my_engine.py
from abevalflow.engines import register_engine
from abevalflow.engines.base import EvalEngine
from abevalflow.gates.base import GateResult, GateType

@register_engine("my-engine")
class MyEngine(EvalEngine):
    name = "my-engine"

    def read_result(self, reports_dir: Path) -> dict | None:
        """Read engine results from reports directory."""
        result_path = reports_dir / "my-engine-report.json"
        if not result_path.exists():
            return None
        return json.loads(result_path.read_text())

    def to_gate_result(self, raw_result: dict, policy: GatePolicy) -> GateResult:
        """Convert engine result to standardized GateResult."""
        score = raw_result.get("score", 0.0)
        threshold = policy.get_gate_policy(self.name).threshold or 0.0

        return GateResult(
            gate_type=GateType.ENGINE,
            gate_name="evaluation",
            policy_key=self.name,
            passed=score >= threshold,
            score=score,
            mode=policy.get_gate_policy(self.name).mode,
            message=f"MyEngine: score={score:.2f}",
        )
```

2. Import in `abevalflow/engines/__init__.py`:

```python
from abevalflow.engines.my_engine import MyEngine
```

## Adding a New Security Gate

1. Create a new file in `abevalflow/gates/security/`:

```python
# abevalflow/gates/security/snyk.py
from abevalflow.gates.security import register_security_gate
from abevalflow.gates.security.base import SecurityGate
from abevalflow.gates.base import GateResult, GateType

@register_security_gate("snyk")
class SnykGate(SecurityGate):
    name = "snyk"

    def evaluate(self, reports_dir: Path, policy: GatePolicy) -> GateResult:
        """Evaluate Snyk security scan results."""
        # Read snyk-report.json and produce GateResult
        ...
```

2. Import in `abevalflow/gates/security/__init__.py`:

```python
from abevalflow.gates.security.snyk import SnykGate
```

## Adding a New Quality Gate

1. Create a new file in `abevalflow/gates/quality/`:

```python
# abevalflow/gates/quality/custom_review.py
from abevalflow.gates.quality import register_quality_gate
from abevalflow.gates.quality.base import QualityGate
from abevalflow.gates.base import GateResult, GateType

@register_quality_gate("custom-review")
class CustomReviewGate(QualityGate):
    name = "custom-review"

    def evaluate(self, workspace_root: Path, policy: GatePolicy) -> GateResult:
        """Evaluate custom quality review results."""
        # Read review artifacts and produce GateResult
        ...
```

2. Import in `abevalflow/gates/quality/__init__.py`:

```python
from abevalflow.gates.quality.custom_review import CustomReviewGate
```

## Adding a New Gate Category

To add an entirely new gate category (e.g., "compliance", "performance"):

1. **Add the GateType enum** in `abevalflow/gates/base.py`:

```python
class GateType(str, Enum):
    ENGINE = "engine"
    SECURITY = "security"
    QUALITY = "quality"
    COMPLIANCE = "compliance"  # New category
```

2. **Create the gate directory** at `abevalflow/gates/compliance/`:

```
abevalflow/gates/compliance/
├── __init__.py      # Registry and exports
├── base.py          # ComplianceGate base class
└── my_checker.py    # First implementation
```

3. **Create the base class** in `abevalflow/gates/compliance/base.py`:

```python
from abc import abstractmethod
from abevalflow.gates.base import GateResult, GateType

class ComplianceGate:
    name: str

    @abstractmethod
    def evaluate(self, reports_dir: Path, policy: GatePolicy) -> GateResult:
        """Evaluate compliance and return standardized GateResult."""
        pass
```

4. **Update the scorecard aggregation** in `scripts/aggregate_scorecard.py`:

```python
from abevalflow.gates.compliance import get_all_compliance_gates

# In aggregate_scorecard():
for compliance_gate in get_all_compliance_gates():
    if not policy.is_enabled(compliance_gate.name):
        continue
    gate_result = compliance_gate.evaluate(reports_dir, policy)
    gates.append(gate_result)
```

5. **Add the category to policy schema** in `abevalflow/schemas.py` (documentation only, the schema is flexible)
