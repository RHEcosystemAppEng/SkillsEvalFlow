# Persistence

## MinIO (Object Storage)

Reports and artifacts are uploaded to MinIO under a timestamped prefix:

```
s3://ab-eval-reports/YYYYMMDD_hhmmss_{submission}_{run-id}/
├── report.json              # Main evaluation report
├── report.md                # Human-readable report
├── scorecard.json           # Unified scorecard
├── security_scans/          # Security scan results
│   └── security-scan.json
├── generated/               # AI-generated artifacts
│   ├── instruction.md
│   └── test_outputs.py
├── scaffolded/              # Scaffolded configs and review
│   └── _ai_review.json
└── trials/                  # Per-trial artifacts (Harbor)
    ├── trial_001/
    │   ├── agent/
    │   └── verifier/
    └── ...
```

## PostgreSQL (Results Database)

Evaluation results are persisted for historical analysis and monitoring:

- **Script:** `scripts/store_results.py`
- **Data stored:**
  - Submission metadata
  - Per-trial results (Harbor/ASE)
  - Security scan findings
  - Aggregate statistics
  - Scorecard recommendation
