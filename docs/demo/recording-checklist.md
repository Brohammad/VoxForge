# Demo Recording Checklist

## Pre-recording

- [ ] Run `./scripts/prove-real-voice.sh https://your-host` with real API keys (automated gate)
- [ ] Set `STT_PROVIDER=deepgram`, `LLM_PROVIDER=openai`, `TTS_PROVIDER=cartesia`, and `DEMO_ENABLED=true` on the recording host
- [ ] Use https://voxforge.brohammad.tech (or local with same UI)
- [ ] Browser: Chrome, 1920×1080, dark mode
- [ ] Confirm the provider badge shows **live** before recording real-provider proof
- [ ] Close unrelated tabs; hide bookmarks
- [ ] Register dashboard account beforehand
- [ ] Upload 1 sample doc to knowledge base
- [ ] Test **Start talking** or **Run trust loop** once (warm cache)

## Recording setup

- [ ] Screen recorder: OBS, Loom, or QuickTime
- [ ] Microphone: clear audio, no background noise
- [ ] Optional: webcam corner for presenter

## 60-second social cut (do this first)

Follow [demo-script-short.md](demo-script-short.md). One video is reused on Twitter, LinkedIn, Reddit, README, and outreach.

- [ ] Record the live site, not slides
- [ ] Hit **Start talking** or **Run trust loop** — never a renamed button
- [ ] Show citation → replay → handoff inbox
- [ ] Burn in captions
- [ ] End card: GitHub URL + `voxforge.brohammad.tech/demo`
- [ ] Export 16:9 MP4 (`demo-showcase-60s.mp4`)

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

Record `/demo`: click **Start talking** (or **Run trust loop** if you cannot use a mic), wait for citations + in-browser TTS, then:

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
