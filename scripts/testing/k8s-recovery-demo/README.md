# k8s-recovery demo fixture

Reproduces the exact bug the `edit_configmap` action was built and live-verified
against: a `checkout-api` pod fails to reach Postgres because its ConfigMap's
`DATABASE_HOST` points at a nonexistent host (`postgres-wrong`), and recovers
the moment that key is corrected back to `postgres`.

Runs against a dedicated `lear-demo` kind cluster/namespace — separate from the
`kind-prash-dev` / `prash-demo` cluster the rest of `scripts/testing/` uses.

```bash
./setup-demo.sh          # creates kind cluster 'lear-demo', deploys postgres + checkout-api
./inject-failure.sh       # patches DATABASE_HOST to the broken value, restarts the deployment
# ... diagnose it: prash fix lear-demo/checkout-api-... (recommends edit_configmap)
./reset-demo.sh           # restores DATABASE_HOST, waits for recovery
```

`manifests/postgres.yaml`'s `POSTGRES_PASSWORD=demo` is a throwaway value for
this local-only cluster, not a real credential.
