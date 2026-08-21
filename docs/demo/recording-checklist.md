# Demo Recording Checklist

## Pre-recording

- [ ] Run `./scripts/prove-real-voice.sh https://your-host` with real API keys (automated gate)
- [ ] Set `STT_PROVIDER=deepgram`, `LLM_PROVIDER=openai`, `TTS_PROVIDER=cartesia`, `DEMO_ENABLED=false` on host
- [ ] Use https://voxforge.brohammad.tech (or local with same UI)
- [ ] Browser: Chrome, 1920×1080, dark mode
- [ ] `DEMO_ENABLED=true` on host (or local)
- [ ] Confirm provider badge shows mock or live before recording
- [ ] Close unrelated tabs; hide bookmarks
- [ ] Register dashboard account beforehand
- [ ] Upload 1 sample doc to knowledge base
- [ ] Test demo call once (warm cache)

## Recording setup

- [ ] Screen recorder: OBS, Loom, or QuickTime
- [ ] Microphone: clear audio, no background noise
- [ ] Optional: webcam corner for presenter

## Assets to capture

| Asset | Duration | Output |
|-------|----------|--------|
| 60s showcase | 60s | `demo-showcase-60s.mp4` |
| 8min walkthrough | 8min | `demo-walkthrough-8min.mp4` |
| Demo GIF | 10–15s | `demo.gif` (from screen recording) |
| Landing hero | Screenshot | `landing-hero.png` ✅ |
| Demo results | Screenshot | `demo-results.png` ✅ |
| Dashboard | Screenshot | `dashboard-overview.png` ✅ |

## GIF creation

**Automated (mock providers, headless):**

```bash
./scripts/generate-demo-gif.sh
```

**Manual (screen recording with real providers):**

Record `/demo`: click **Run one-click sample call**, wait for chat + in-browser TTS, then:

```bash
./scripts/capture-demo-gif.sh ~/Movies/demo-recording.mp4
```

Manual ffmpeg (alternative):

```bash
ffmpeg -i demo-showcase-60s.mp4 -vf "fps=10,scale=800:-1" -loop 0 demo.gif
```

## Post-production

- [ ] Add title card: "VoxForge — Voice AI Infrastructure"
- [ ] Add end card: GitHub URL + live demo URL
- [ ] Upload to `docs/assets/` and link from README
- [ ] Compress for web (< 5MB GIF)

## Presenter notes

See [presenter-notes.md](presenter-notes.md).
