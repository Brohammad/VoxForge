# Design Partner Documentation

Guides for pilot customers evaluating VoxForge for production voice agents.

## Pilot journey

| Phase | Document |
|-------|----------|
| 1. Kickoff | [onboarding-guide.md](onboarding-guide.md) |
| 2. Admin setup | [admin-guide.md](admin-guide.md) |
| 3. Day-to-day ops | [operator-guide.md](operator-guide.md) |
| 4. End users | [end-user-guide.md](end-user-guide.md) — see demo + dashboard |
| 5. Measure success | [success-metrics.md](success-metrics.md) |
| 6. Close pilot | [feedback-questionnaire.md](feedback-questionnaire.md) |

## Business case

| Document | Purpose |
|----------|---------|
| [roi-calculator.md](roi-calculator.md) | ROI worksheet |
| [case-study-template.md](case-study-template.md) | Post-pilot write-up |
| [../benchmarks/competitive-analysis.md](../benchmarks/competitive-analysis.md) | vs Vapi, Retell, LiveKit Agents |
| [../product/prove-value-in-1-day.md](../product/prove-value-in-1-day.md) | 1-day value checklist |

## Shared demo environment

Try without deploying:

- **Demo:** https://voxforge.brohammad.tech/demo
- **Dashboard:** https://voxforge.brohammad.tech/dashboard
- **Credentials:** register your own account, or use `demo@voxforge.io` on the public instance

## Dedicated deployment

```bash
./scripts/setup-production-env.sh your-company.example.com
./deploy.sh init
```

See [../deployment/guide.md](../deployment/guide.md) and [../deployment/verification-checklist.md](../deployment/verification-checklist.md).

## Request a pilot

Open a [GitHub issue](https://github.com/Brohammad/VoxForge/issues/new?template=feature_request.md) or [Discussion](https://github.com/Brohammad/VoxForge/discussions).
