# LiveKit WebRTC Client Example

Browser demo for VoxForge WebRTC voice sessions using the [LiveKit JavaScript SDK](https://docs.livekit.io/client-sdk-js/).

## Prerequisites

1. VoxForge API running (`docker compose up -d`)
2. LiveKit Cloud project (or self-hosted LiveKit server)
3. LiveKit agent worker: `make livekit-worker`
4. JWT access token from `POST /api/v1/auth/login`

Set in `.env`:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_AGENT_NAME=voxforge-voice
```

## Usage

Open http://localhost:8000/examples/livekit

1. Paste your JWT access token
2. Set participant identity (defaults to a random `user-*` id)
3. Click **Start WebRTC Session**

The client will:

- Create a `webrtc` transport session via the VoxForge API
- Fetch a LiveKit participant token (and dispatch the agent worker)
- Connect to the room and publish your microphone
- Hear agent audio published by the VoxForge LiveKit worker

## Flow

```
Browser          VoxForge API       LiveKit SFU       LiveKit Worker
   | POST /sessions/webrtc  |              |                  |
   |---------------------->|              |                  |
   | POST /livekit/token    | dispatch     |                  |
   |---------------------->|------------->| job for room     |
   | connect(url, token)    |              |                  |
   |--------------------------------------->|                  |
   | publish mic            |              | subscribe audio  |
   |--------------------------------------->|----------------->|
   |                        |              |    VoicePipeline |
   |<-------------------------------------- agent audio track |
```

## Notes

- The browser SDK is vendored at `static/livekit-client.umd.min.js` (no CDN required).
- The worker bridges room audio into `VoicePipelineService` (same stack as WebSocket voice).
- For WebSocket voice, use `/api/v1/ws/voice` instead.
- See `docs/architecture/livekit-integration.md` for failure modes and observability.
