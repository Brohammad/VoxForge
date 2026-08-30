# VoxForge Roadmap

## v1.0.0 (RC-1 → GA)

- [x] Production deployment automation (`deploy.sh`, TLS, NGINX)
- [x] Playwright browser test suite in CI
- [x] Security headers + CSP + production env validation
- [x] Open-source governance (CONTRIBUTING, SECURITY, CHANGELOG)
- [x] HttpOnly cookie auth for dashboard (Bearer still supported)
- [x] Org email invite + accept flow
- [ ] LiveKit WebRTC end-to-end validation with real audio
- [x] Zendesk adapter implementation + unit tests (create/lookup + handoff replay context)
- [ ] Zendesk production proof: verify the adapter against a live sandbox
- [ ] Freshdesk adapter
- [x] Collection delete API for knowledge base
- [ ] Nightly CI: live provider + load smoke jobs

## v1.1

- Playwright coverage for SSO admin flows
- Horizontal scaling guide (multi-worker + sticky sessions)

## v1.2

- Self-hosted LiveKit server compose profile
- OpenTelemetry collector compose profile
- Enterprise audit log export scheduling

## Non-goals

- Multi-tenant SaaS billing
- Custom model fine-tuning UI
- Non-voice chat-only mode as primary product
