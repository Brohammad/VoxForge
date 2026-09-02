# VoxForge Documentation

**Live demo:** https://voxforge.brohammad.tech/demo · **API:** https://voxforge.brohammad.tech/api/v1/docs · **Release:** [v1.0.0-rc.1](release/v1.0.0-rc.1.md)

---

## Start here

| I want to… | Go to |
|------------|-------|
| Run VoxForge locally in 15 minutes | [ONBOARDING.md](ONBOARDING.md) |
| Record a 60-second demo | [demo/demo-script-short.md](demo/demo-script-short.md) |
| Deploy to production with HTTPS | [deployment/guide.md](deployment/guide.md) |
| Understand the architecture | [architecture/README.md](architecture/README.md) |
| Configure environment variables | [CONFIGURATION.md](CONFIGURATION.md) |
| Operate a running deployment | [operations/runbook.md](operations/runbook.md) |
| Onboard a design partner | [pilot/onboarding-guide.md](pilot/onboarding-guide.md) |
| Run or extend tests | [testing/README.md](testing/README.md) |
| See what's not ready yet | [release/known-limitations.md](release/known-limitations.md) |

---

## By audience

### Developers

- [15-minute onboarding](ONBOARDING.md)
- [Configuration reference](CONFIGURATION.md)
- [Testing guide](testing/README.md)
- [Architecture index](architecture/README.md)
- [ADRs](adr/README.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)

### Operators & DevOps

- [Deployment guide](deployment/guide.md)
- [Production runbook](operations/runbook.md)
- [Verification checklist](deployment/verification-checklist.md)
- [Troubleshooting](deployment/troubleshooting.md)
- [Backup & restore](operations/backup-restore.md)
- [Incident response](operations/incident-response.md)
- [Disaster recovery](operations/disaster-recovery.md)
- [Public deployment record](deployment/public-deployment-record.md)

### Founders & design partners

- [Pilot onboarding](pilot/onboarding-guide.md)
- [Prove value in 1 day](product/prove-value-in-1-day.md)
- [Success metrics](pilot/success-metrics.md)
- [Competitive benchmark](benchmarks/competitive-analysis.md)
- [Demo scripts](demo/README.md)

### Contributors

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [SECURITY.md](../SECURITY.md)
- [Testing strategy](testing/testing-strategy.md)
- [Roadmap](ROADMAP.md)
- [Good first issues](https://github.com/Brohammad/VoxForge/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)

---

## Documentation map

```
docs/
├── README.md              ← you are here
├── ONBOARDING.md          Quick local setup
├── CONFIGURATION.md       Environment variables
├── FAQ.md                 Common questions
├── ROADMAP.md             Product roadmap
│
├── architecture/          System design
├── deployment/            Install & deploy
├── operations/            Day-2 ops & incidents
├── testing/               Test strategy & reports
├── pilot/                 Design partner guides
├── demo/                  Demo scripts & recording
├── release/               Release notes & limitations
├── benchmarks/            Performance & competitive analysis
├── product/               Product checklists
├── adr/                   Architecture decision records
├── launch/                Launch checklists (RC-1)
└── portfolio/             Resume & interview materials
```

---

## Reference deployment

| Item | Value |
|------|-------|
| URL | https://voxforge.brohammad.tech |
| Health | `/api/v1/health` |
| Readiness | `/api/v1/ready` |
| TLS | Let's Encrypt (auto-renew) |
| Docs | [public-deployment-record.md](deployment/public-deployment-record.md) |

---

## API documentation

Interactive OpenAPI is served at `/api/v1/docs` on any running instance. No separate API doc site — the spec is the source of truth.

---

## Changelog & releases

| Document | Description |
|----------|-------------|
| [CHANGELOG.md](../CHANGELOG.md) | Full change history |
| [v1.0.0-rc.1](release/v1.0.0-rc.1.md) | Current release notes |
| [RC-1 report](release/RC-1-REPORT.md) | Production readiness audit |
| [Known limitations](release/known-limitations.md) | Honest gaps for v1.0 |
