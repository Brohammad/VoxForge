# Launch Checklist — VoxForge v1.0 RC

## Public deployment

- [x] Live at https://voxforge.brohammad.tech
- [x] HTTPS + HSTS
- [x] Health `/api/v1/health` → ok
- [x] Readiness `/api/v1/ready` → ok
- [x] Push RC-1 commits to `origin/main`
- [x] Redeploy VPS with new landing page + screenshots
- [x] Verify Certbot auto-renewal (cert valid until 2026-10-08)

## Public website

- [x] Product landing page (hero, features, architecture, FAQ)
- [x] Screenshots captured
- [x] Demo GIF generated (`docs/assets/screenshots/demo.gif`)
- [ ] Demo video recorded (MP4 — optional; see `docs/demo/recording-checklist.md`)
- [x] GitHub, docs, API links

## Quality gates

- [x] 378 pytest (excl. browser)
- [x] 8 Playwright browser tests
- [x] Ruff clean
- [x] 81% coverage (70% gate)
- [x] pip-audit + gitleaks in CI
- [x] Dockerfile.prod builds

## Open source

- [x] README with badges + quick start
- [x] CONTRIBUTING, SECURITY, CODE_OF_CONDUCT
- [x] CHANGELOG RC-1
- [x] Issue + PR templates
- [ ] GitHub Discussions enabled
- [x] Repository topics set (`scripts/github-oss-polish.sh`)
- [x] GitHub Release `v1.0.0-rc.1` (tag pushed; create release on GitHub)
- [x] Good first issues filed (#7–#10)

## Documentation

- [x] Deployment guide + troubleshooting
- [x] Production runbook
- [x] Incident response + DR
- [x] Pilot onboarding guide
- [x] Demo scripts
- [x] Competitive benchmark
- [x] Launch readiness review

## Pilot readiness

- [x] Shared demo environment live
- [x] Pilot onboarding guide
- [x] Success metrics + ROI calculator
- [x] Case study template
- [x] Feedback questionnaire

## Portfolio

- [x] Resume bullets
- [x] Interview prep
- [x] Architecture diagrams (mermaid)

## Sign-off

| Role | Status |
|------|--------|
| Founding Engineer | RC-1 approved |
| DevOps | Deploy live, redeploy pending push |
| Product | Website ready, video pending |
| QA | Tests green |

**Tag `v1.0.0-rc.1` after:** push + VPS redeploy + optional demo video.
