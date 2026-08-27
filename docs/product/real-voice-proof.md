# Real-provider voice proof

Two layers of proof for sales, pilots, and resume. This does not redeploy the VPS — it proves whatever host you pass in.

1. **Automated (no mic)** — [scripts/prove-real-voice.sh](../../scripts/prove-real-voice.sh)
2. **Recorded demo (mic + UI)** — [recording-checklist.md](../demo/recording-checklist.md)

## Automated proof

On a server with real keys:

```bash
export STT_PROVIDER=deepgram
export LLM_PROVIDER=openai
export TTS_PROVIDER=cartesia
export DEEPGRAM_API_KEY=...
export OPENAI_API_KEY=...
export CARTESIA_API_KEY=...

./scripts/prove-real-voice.sh https://your-domain.example
```

Leave `DEMO_ENABLED=true` on the public demo host if you also want the script to hit `POST /api/v1/demo/trust-loop` (cite → replay → handoff). Set `DEMO_ENABLED=false` only on a locked-down pilot host that should not expose the unauthenticated demo.

Success criteria:

- `/api/v1/ready` → `database` + `redis` ok
- `POST /api/v1/onboarding/run-sample-call` → `test_call_passed`
- Session has ≥2 messages (user + assistant)
- If demo is enabled: trust loop returns citations + replay URL

## Recorded demo (portfolio / MVP)

Capture after automated proof passes:

| Step | Action |
|------|--------|
| 1 | Set real providers on demo host (or use pilot env) |
| 2 | Open `/demo` |
| 3 | **Start talking**, or **Run trust loop** |
| 4 | Show citations + Open replay / Open inbox |
| 5 | Export 10–15s GIF → `docs/assets/screenshots/demo.gif` |
| 6 | Update README hero GIF link |

Automated mock GIF: `./scripts/generate-demo-gif.sh` (records the trust-loop button).

## Resume bullet (when both done)

> Shipped self-hosted voice AI with real Deepgram/OpenAI/Cartesia providers, automated proof script, and recorded end-to-end demo on production HTTPS.
