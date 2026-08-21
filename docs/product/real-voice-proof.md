# Real-provider voice proof

Two layers of proof for sales, pilots, and resume:

1. **Automated (no mic)** — [scripts/prove-real-voice.sh](../../scripts/prove-real-voice.sh)
2. **Recorded demo (mic + UI)** — [recording-checklist.md](../demo/recording-checklist.md)

## Automated proof

On a server with real keys and mock providers disabled:

```bash
export STT_PROVIDER=deepgram
export LLM_PROVIDER=openai
export TTS_PROVIDER=cartesia
export DEMO_ENABLED=false
export DEEPGRAM_API_KEY=...
export OPENAI_API_KEY=...
export CARTESIA_API_KEY=...

./scripts/prove-real-voice.sh https://your-domain.example
```

Success criteria:

- `/api/v1/ready` → `database` + `redis` ok
- `POST /api/v1/onboarding/run-sample-call` → `test_call_passed`
- Session has ≥2 messages (user + assistant)

## Recorded demo (portfolio / MVP)

Capture after automated proof passes:

| Step | Action |
|------|--------|
| 1 | Set real providers on demo host (or use pilot env) |
| 2 | Open `/demo` or dashboard onboarding |
| 3 | Run a call; show transcript + latency |
| 4 | Export 10–15s GIF → `docs/assets/screenshots/demo.gif` |
| 5 | Update README hero GIF link |

Use the ffmpeg command in [recording-checklist.md](../demo/recording-checklist.md).

## Resume bullet (when both done)

> Shipped self-hosted voice AI with real Deepgram/OpenAI/Cartesia providers, automated proof script, and recorded end-to-end demo on production HTTPS.
