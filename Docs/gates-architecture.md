# Gates Architecture

Gates are evaluation checkpoints that produce standardized results. The unified scorecard aggregates all gate results to produce a final recommendation.

## Gate Types

| Category | Policy Key | Purpose | Implementation |
|----------|------------|---------|----------------|
| **evaluation** | `evaluation` | Results from the selected eval engine | Harbor, ASE, A2A, MCPChecker, or AEH |
| **security** | `security` | Security scanning results | Cisco AI Defense scanner, [harness-eval](https://github.com/redhat-community-ai-tools/harness-eval) deterministic scanner |
| **quality** | `quality` | Quality review results | LLM-powered review, [harness-eval](https://github.com/redhat-community-ai-tools/harness-eval) deterministic quality checks |

## Gate Modes

Each gate operates in one of three modes:

| Mode | Behavior |
|------|----------|
| `disabled` | Gate is skipped entirely |
| `warn` | Gate runs; failures produce warnings but don't block |
| `block` | Gate runs; failures cause the scorecard to fail |

## GateResult Schema

All gates produce a standardized `GateResult`:

```python
class GateResult:
    gate_type: GateType      # engine, security, or quality
    gate_name: str           # Category name: "evaluation", "security", or "quality"
    policy_key: str          # Implementation: "harbor", "cisco", "llm-review", etc.
    passed: bool             # Whether the gate passed
    score: float             # Normalized score (0.0 to 1.0)
    mode: GateMode           # Mode that was applied (disabled/warn/block)
    threshold: float | None  # Threshold used for pass/fail
    findings: list[Finding]  # Issues discovered (security/quality gates)
    details: dict            # Implementation-specific data (e.g., {"engine": "harbor"})
    message: str             # Human-readable summary
```

The `gate_name` is the category used in policy configuration, while `policy_key` identifies the specific implementation.

## Existing Gates

### Evaluation Gate (`evaluation`)

The primary gate that wraps the selected evaluation engine's results.

- **Location:** `abevalflow/engines/*.py` (each engine produces evaluation gate results)
- **Input:** Engine-specific report from `reports/{submission}/`
- **Engines:** Harbor, ASE, A2A, MCPChecker (selected via `eval_engine` in metadata.yaml)
- **Pass criteria:**
  - Harbor/ASE/A2A: `treatment_score - control_score >= threshold` (default threshold: 0.0)
  - MCPChecker: All tasks pass verification
- **Score:** Mean reward or pass rate depending on engine

### Security Gate (`security`)

Two scanners feed into the security gate:

**Cisco AI Defense** (`CiscoGate`):
- **Location:** `abevalflow/gates/security/cisco.py`
- **Input:** `reports/{submission}/security-scan.json`
- **Scanner:** Cisco AI Defense model-based detection

**harness-eval** (`SkillMdScannerGate`):
- **Location:** `abevalflow/gates/security/skillmd_scanner.py`
- **Input:** `reports/{submission}/skillmd-security-scan.json`
- **Scanner:** [harness-eval](https://github.com/redhat-community-ai-tools/harness-eval) `skill-submission-scan` CLI (27 rule categories, 97 deterministic rules)
- **Includes:** Optional LLM semantic security review (anti-jailbreak, semantic attacks, description-behavior mismatch)

Both gates use the same pass criteria:
- `warn` mode: Always passes (findings are advisory)
- `block` mode: Fails if any HIGH or CRITICAL findings exist
- **Score:** Weighted average based on finding severities

### Quality Gate (`quality`)

Two sources feed into quality gates:

**LLM Quality Review** (`LLMReviewGate`):
- **Location:** `abevalflow/gates/quality/llm_review.py`
- **Input:** `{workspace}/_ai_review.json`
- **Dimensions evaluated:** coherence, coverage, clarity, feasibility, robustness
- **Default threshold:** 0.6

**harness-eval Quality** (`SkillMdQualityGate`):
- **Location:** `abevalflow/gates/quality/skillmd_quality.py`
- **Input:** `{workspace}/skillmd-quality-scan.json`
- **Checks:** description quality, broken references, imprecise instructions, unfinished content, stale references, scope overreach, token budget, and more

## Scorecard

The scorecard is the single source of truth for submission evaluation, aggregating all gate results with configurable policy.

### Scorecard Schema

```python
class Scorecard:
    submission_name: str           # Name of the evaluated submission
    pipeline_run_id: str           # Tekton PipelineRun ID
    eval_engine: str               # Primary evaluation engine used
    gates: list[GateResult]        # All gate results
    policy: GatePolicy             # Policy that was applied
    recommendation: Recommendation # pass, warn, or fail
    recommendation_reason: str     # Human-readable explanation
    gates_passed: int              # Count of passed gates
    gates_failed: int              # Count of failed gates
    blocking_gates_passed: int     # Count of passed blocking gates
    blocking_gates_failed: int     # Count of failed blocking gates
```

### Combination Modes

| Mode | Logic |
|------|-------|
| `all_pass` | All blocking gates must pass; failing warn gates produce warnings |
| `any_pass` | At least one blocking gate must pass |
| `weighted` | Weighted average of gate scores determines outcome |

### Output

The scorecard is written to `reports/{submission}/scorecard.json` and includes:
- All gate results with scores and findings
- Final recommendation with reasoning
- Provenance metadata (commit SHA, branch, pipeline run ID)

## Gate Policy Configuration

Gate policies are configured in `metadata.yaml` under the `gate_policy` key:

```yaml
# metadata.yaml
name: my-skill
eval_engine: harbor

gate_policy:
  default_mode: warn           # Default mode for all gates
  combination: all_pass        # How to combine gate results

  gates:
    # Security gate configuration
    security:
      mode: block              # Fail the scorecard on security issues
      threshold: 0.8           # Minimum score to pass

    # Quality gate configuration
    quality:
      mode: warn               # Advisory only
      threshold: 0.6           # Threshold for pass/fail

    # Engine gate configuration (uses eval_engine automatically)
    evaluation:
      mode: block
      threshold: 0.0           # Any positive uplift passes
```

### GatePolicyItem Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `disabled`/`warn`/`block` | `warn` | Enforcement mode |
| `threshold` | `float` | Gate-specific | Score threshold for pass/fail |
| `weight` | `float` | `1.0` | Weight for weighted combination mode |
