# Load Testing

Repeatable load test scaffolding lives in `scripts/load/`. Tests use mock providers and target a running VoxForge instance.

## Locust

```bash
pip install locust
docker compose up -d
locust -f scripts/load/locustfile.py --host http://127.0.0.1:8000
```

Headless smoke (10 users, 30s):

```bash
locust -f scripts/load/locustfile.py --host http://127.0.0.1:8000 \
    --headless -u 10 -r 2 -t 30s --csv=load-results
```

The same cheap headless command runs in `.github/workflows/nightly-smoke.yml` (schedule + `workflow_dispatch`, mock providers). Paid live-provider smoke is secrets-gated on that workflow and is not on `pull_request`.

### Tasks weighted

| Task | Weight | Endpoint |
|------|--------|----------|
| Health | 3 | `GET /api/v1/health` |
| Session create | 2 | `POST /api/v1/sessions` |
| Dashboard | 2 | `GET /api/v1/dashboard/outcomes` |
| Knowledge search | 1 | `POST /api/v1/knowledge/search` |
| Replay | 1 | `GET /api/v1/sessions/{id}/replay` |

Set `VOXFORGE_LOAD_TOKEN` to skip registration per virtual user.

## k6

```bash
k6 run scripts/load/k6_smoke.js
# custom host:
VOXFORGE_BASE_URL=http://127.0.0.1:8000 k6 run scripts/load/k6_smoke.js
```

### Metrics

- `session_create_latency` (p99 < 3s threshold)
- `knowledge_search_latency`
- `errors` rate (< 10%)
- Built-in `http_req_duration` p95 < 2s

## Micro-benchmarks (CI)

| Script | CI job |
|--------|--------|
| `scripts/benchmark_onboarding.py` | `benchmark-onboarding` |
| `scripts/benchmark_knowledge_base.py` | `benchmark-knowledge-base` |

These report mean, p50, p95 for programmatic pipeline paths without external APIs.

## Known ceiling

Single uvicorn worker; ~50 concurrent WebSocket sessions is documented but not load-verified. Run Locust/k6 before production traffic.
