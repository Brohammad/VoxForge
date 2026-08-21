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
- [ ] Browser TTS via `/demo/speak` (retire `afplay` on public path)
- [ ] Mock vs real provider badges on landing and demo
- [ ] Align Playwright + docs with “Run one-click sample call”

## Stage 4 — Knowledge completeness
- [ ] `GET /knowledge/collections/{id}/documents` list API
- [ ] `DELETE` collection and document APIs
- [ ] Dashboard document table (replace localStorage catalog)

## Stage 5 — Dashboard auth UX
- [ ] Hide JWT paste behind Advanced
- [ ] Register UI on dashboard
- [ ] Invite accept form (replace API-only deep link)
- [ ] API keys management page

## Stage 6 — Product polish
- [ ] Orchestrator mode toggle in dashboard (single vs multi_agent)
- [ ] Collapse nav to Talk / Knowledge / Inbox / Settings
- [ ] Remove or implement Zendesk ticket language
- [ ] Real-provider demo recording + README GIF refresh

## Non-goals (do not build yet)
- Multi-tenant billing / hosted SaaS
- Visual flow builder
- React dashboard rewrite
- Hybrid retrieval / S3 blobs (post-MVP)
