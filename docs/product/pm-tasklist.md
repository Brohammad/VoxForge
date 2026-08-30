# VoxForge PM Tasklist

Prioritized implementation plan from the RC-1 product review. Each stage ends with a git commit and push.

## Stage 1 — Critical bugfixes (Week 1)
- [x] Fix cookie-session dashboard nav (`isAuthenticated()` not `token`)
- [x] Public SAML begin-login (cold IdP SSO)
- [x] Remove `.docx` from file pickers until parser exists
- [x] Honor `#replay=` and `#session=` dashboard deep links

## Stage 2 — Wire policy presets into live pipeline
- [x] Load `AgentConfigService.get_active()` in pipeline factory
- [x] Apply `system_prompt` and `orchestrator_mode` per org/session
- [x] Alerts read active agent `eval_thresholds`

## Stage 3 — Demo voice + honest labeling
- [x] Browser TTS via `/demo/speak` (retire `afplay` on public path)
- [x] Mock vs real provider badges on demo page
- [x] Align Playwright + key docs with “Run one-click sample call”

## Stage 4 — Knowledge completeness
- [x] `GET /knowledge/collections/{id}/documents` list API
- [x] `DELETE` collection and document APIs
- [x] Dashboard document table (replace localStorage catalog)

## Stage 5 — Dashboard auth UX
- [x] Hide JWT paste behind Advanced
- [x] Register UI on dashboard
- [x] Invite accept form (replace API-only deep link)
- [x] API keys management page

## Stage 6 — Product polish
- [x] Orchestrator mode visible on policy presets and active config
- [x] Collapse nav to Talk / Knowledge / Inbox / Settings
- [x] Honest ticketing language on landing and competitive docs
- [x] Real-provider demo recording + README GIF refresh (`./scripts/generate-demo-gif.sh` for mock UI capture; `./scripts/capture-demo-gif.sh` for manual recordings)

## Stage 12 — Demo GIF assets
- [x] Automated headless Playwright recorder (`scripts/record_demo_gif.py`)
- [x] One-command generator (`scripts/generate-demo-gif.sh`)
- [x] Committed `docs/assets/screenshots/demo.gif` + `public/assets/screenshots/demo.gif`

## CI / merge readiness
- [x] Stage 9: Ruff format + EMBEDDING_PROVIDER in CI/conftest
- [x] Stage 10: Browser tests + logout race fix for hub nav / demo TTS
- [x] Stage 11: Disable rate limiting in browser CI (dashboard 429 fix)
- [x] All CI checks green on PR #2 — marked ready for review

## Stage 13 — Portfolio & OSS polish
- [x] Interview case study (`docs/portfolio/case-study.md`)
- [x] Portfolio index + updated resume kit / interview prep (386+ tests)
- [x] README test count + GIF refresh docs
- [x] GitHub topics + good first issues (`scripts/github-oss-polish.sh` — issues #7–#10)

## Stage 14 — Public voice UX
- [x] Browser microphone capture on `/demo`
- [x] Speech input runs through STT → agent → browser TTS
- [x] Typed chat remains available as a fallback

## Stage 15 — Public trust loop
- [x] Seed and cite a demo FAQ
- [x] Link the completed session to replay
- [x] Create a handoff and link it to Inbox

## Stage 16 — Production knowledge reliability
- [x] Enable the knowledge worker in production defaults
- [x] Persist knowledge blobs outside `/tmp`
- [x] Validate production config when knowledge is enabled without a worker

## Stage 17 — Real-provider proof workflow
- [x] Point proof and GIF scripts at the public trust loop
- [ ] Run `./scripts/prove-real-voice.sh` against production with real provider keys
- [ ] Replace the mock-provider GIF with a real-provider recording

## Stage 18 — Visible multi-agent demo
- [x] Run `/demo` sessions through the LangGraph multi-agent path
- [x] Exercise `knowledge_base_lookup` with mock providers
- [x] Display planner / tool / critic trace in the public demo

## Deployment / GTM
- [ ] Redeploy `voxforge.brohammad.tech` from current `main`
- [ ] Verify microphone, trust loop, replay, handoff, and knowledge ingestion on production
- [ ] Record the 60-second showcase video (issue #8)
- [ ] Send three targeted founder / engineer outreach messages using the live proof

## Non-goals (do not build yet)
- Multi-tenant billing / hosted SaaS
- Visual flow builder
- React dashboard rewrite
- Hybrid retrieval / S3 blobs (post-MVP)
