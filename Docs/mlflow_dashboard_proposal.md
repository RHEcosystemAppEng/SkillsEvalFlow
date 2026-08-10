# MLflow Dashboard Proposal — ABEvalFlow Observability

Phase C+D of APPENG-5370. Using MLflow's built-in dashboard and experiment tracking to visualize pipeline results, gate scores, certification levels, and LLM token usage — all in one place.

Each pipeline run becomes an MLflow run under an experiment (one experiment per submission). Metrics are logged from our existing PostgreSQL tables.

Please review and share feedback or additional metrics you'd like to see.

---

## Experiment-Level View (per submission)

Each submission (e.g. `hello-world`, `my-skill`) is an MLflow experiment. Every pipeline run is a run within that experiment, enabling run-to-run comparison.

### Logged per run

**Parameters (static per run):**
| Parameter | Source |
|-----------|--------|
| `eval_engine` | `scorecards.eval_engine` |
| `combination_mode` | `scorecards.combination_mode` |
| `pipeline_run_id` | `scorecards.pipeline_run_id` |
| `commit_sha` | `evaluation_runs.commit_sha` |
| `model_name` | `observability_metrics.model_name` |

**Metrics (tracked over runs):**
| Metric | Source | What it shows |
|--------|--------|---------------|
| `recommendation` | `scorecards.recommendation` | pass/warn/fail verdict |
| `uplift` | `evaluation_runs.uplift` | Treatment vs control pass rate difference |
| `treatment_pass_rate` | `evaluation_runs.treatment_pass_rate` | How often treatment variant passed |
| `control_pass_rate` | `evaluation_runs.control_pass_rate` | How often control variant passed |
| `mean_reward_gap` | `evaluation_runs.mean_reward_gap` | Reward score difference between variants |
| `ttest_p_value` | `evaluation_runs.ttest_p_value` | Statistical significance of reward difference |
| `fisher_p_value` | `evaluation_runs.fisher_p_value` | Statistical significance of pass rate difference |
| `gates_passed` | `scorecards.gates_passed` | How many gates passed |
| `gates_failed` | `scorecards.gates_failed` | How many gates failed |
| `highest_certification` | `scorecards.highest_certification` | Best certification level achieved |
| `gate_score_evaluation` | `gate_results.score` where gate_name=evaluation | Engine gate score (0-1) |
| `gate_score_security` | `gate_results.score` where gate_name=security | Security gate score (0-1) |
| `gate_score_quality` | `gate_results.score` where gate_name=quality | Quality gate score (0-1) |
| `gate_score_behavioral` | `gate_results.score` where gate_name=behavioral | Behavioral gate score (0-1) |
| `security_findings_count` | `gate_results.findings_count` where gate_type=security | Number of security issues found |
| `total_prompt_tokens` | `observability_metrics.total_prompt_tokens` | Prompt tokens sent to LLM |
| `total_completion_tokens` | `observability_metrics.total_completion_tokens` | Completion tokens from LLM |
| `total_tokens` | `observability_metrics.total_tokens` | Total LLM tokens used |
| `llm_calls_count` | `observability_metrics.llm_calls_count` | Number of LLM API calls |
| `certification_foundational_passed` | `certifications` where level=foundational | Whether foundational checks passed |
| `certification_trusted_passed` | `certifications` where level=trusted | Whether trusted checks passed |
| `certification_certified_passed` | `certifications` where level=certified | Whether certified checks passed |

**Artifacts (attached per run):**
| Artifact | Description |
|----------|-------------|
| `scorecard.json` | Full scorecard with all gate results |
| `report.md` | Human-readable evaluation report |
| `report.json` | Machine-readable evaluation report |

**Tags:**
| Tag | Value |
|-----|-------|
| `recommendation` | pass / warn / fail |
| `eval_engine` | harbor / ase / aeh / a2a / mcpchecker |
| `highest_certification` | none / foundational / trusted / certified |

---

## What MLflow shows out of the box with this data

### Run comparison
- Compare any two runs side-by-side: metrics, parameters, artifacts
- See how uplift, pass rate, and gate scores changed between runs

### Metric charts (built-in)
- `treatment_pass_rate` over runs — is the skill improving?
- `gate_score_security` over runs — are security scores trending up?
- `total_tokens` over runs — is token usage growing?
- `uplift` over runs — is the skill's impact stable?

### Experiment overview
- Table of all runs with sortable columns (pass rate, uplift, certification, tokens)
- Filter by tags (e.g. show only failed runs, or only harbor engine)

### Cost tracking
- `total_tokens` and `total_prompt_tokens` / `total_completion_tokens` per run
- Compare token usage across submissions to identify expensive evaluations

---

## Summary

| What | Where it comes from | What question it answers |
|------|-------------------|------------------------|
| Pass/fail trends | `scorecards.recommendation` | Is the pipeline healthy? |
| Skill improvement | `evaluation_runs.uplift`, `treatment_pass_rate` | Are skills getting better over time? |
| Gate health | `gate_results.score`, `gate_results.passed` | Which gates fail most? Are scores improving? |
| Certification progress | `certifications.passed`, `scorecards.highest_certification` | What levels are submissions reaching? |
| Token/cost tracking | `observability_metrics.total_tokens`, `llm_calls_count` | How much are evaluations costing? |
| Security trends | `gate_results.findings_count` where security | Are submissions getting more secure? |
