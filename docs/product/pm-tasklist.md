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
- [ ] Collapse nav to Talk / Knowledge / Inbox / Settings (deferred — large IA change)
- [x] Honest ticketing language on landing and competitive docs
- [ ] Real-provider demo recording + README GIF refresh (deferred)

## Non-goals (do not build yet)
- Multi-tenant billing / hosted SaaS
- Visual flow builder
- React dashboard rewrite
- Hybrid retrieval / S3 blobs (post-MVP)
