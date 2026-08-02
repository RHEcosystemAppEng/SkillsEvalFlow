# ABEvalFlow MLflow (eval-only)

Lightweight tracking server for AEH post-evaluate logging. **Not** production
telemetry HA — single replica, SQLite on a PVC.

## Apply (in-cluster CI)

```bash
oc apply -f config/mlflow/pvc.yaml
oc apply -f config/mlflow/service.yaml
oc apply -f config/mlflow/deployment.yaml
```

Pipeline tracking URI (ClusterIP):

```text
http://abevalflow-mlflow.ab-eval-flow.svc.cluster.local:5000
```

Set pipeline params `enable-mlflow=true` and `mlflow-tracking-uri` to that URL.

## Security defaults

- `--allowed-hosts` lists in-cluster Service DNS + localhost only (no `*`).
- CORS wildcards are **not** enabled; browser UIs need an explicit allowlist.
- `route.yaml` is **optional / dev-only**. Do not apply it unless you also
  append the Route hostname to `--allowed-hosts` in `deployment.yaml`.

## Storage

`pvc.yaml` sets `storageClassName: gp3` (AWS). On other clusters, edit or omit
the field so the cluster default StorageClass applies.
