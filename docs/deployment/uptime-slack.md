# Uptime alerts → Slack

Wire external uptime monitoring to Slack for pilot/production hosts.

## Option A — UptimeRobot → Slack (recommended)

1. In [UptimeRobot](https://uptimerobot.com/), create an **HTTP(s)** monitor:
   - URL: `https://<your-domain>/api/v1/ready`
   - Interval: 5 minutes
   - Alert when down: **2 consecutive failures**

2. In UptimeRobot → **My Settings → Alert Contacts → Add Alert Contact → Slack**:
   - Authorize your workspace
   - Pick `#ops` or `#alerts`

3. Attach the Slack contact to the monitor.

UptimeRobot sends down/up messages automatically; no custom script required.

## Option B — Cron + Slack webhook

Use [scripts/uptime-ready-check.sh](../../scripts/uptime-ready-check.sh) on a small VM or GitHub Actions schedule:

```bash
chmod +x scripts/uptime-ready-check.sh
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../..."
./scripts/uptime-ready-check.sh https://voxforge.brohammad.tech
```

Create the Slack webhook: **Slack app → Incoming Webhooks → Add to workspace**.

### Cron (every 5 minutes)

```cron
*/5 * * * * SLACK_WEBHOOK_URL=https://hooks.slack.com/... /path/to/VoxForge/scripts/uptime-ready-check.sh https://your-domain.example >> /var/log/voxforge-uptime.log 2>&1
```

## Option C — Healthchecks.io ping

After a successful ready check, ping Healthchecks.io (see [uptime.md](./uptime.md)).

## Message format

Slack messages include the failing URL. Extend `uptime-ready-check.sh` with `@channel` or PagerDuty webhooks if needed.

## Related

- [uptime.md](./uptime.md) — health vs ready endpoints
- [deploy-smoke workflow](../../.github/workflows/deploy-smoke.yml) — post-release compose smoke
