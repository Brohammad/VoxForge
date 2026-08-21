# Release Documentation

## Current release

| Item | Link |
|------|------|
| **Version** | v1.0.0-rc.1 |
| **Release notes** | [v1.0.0-rc.1.md](v1.0.0-rc.1.md) |
| **GitHub Release** | https://github.com/Brohammad/VoxForge/releases/tag/v1.0.0-rc.1 |
| **Live instance** | https://voxforge.brohammad.tech |

## Reports

| Document | Description |
|----------|-------------|
| [RC-1-REPORT.md](RC-1-REPORT.md) | Full RC-1 production readiness audit |
| [known-limitations.md](known-limitations.md) | Honest gaps for v1.0 |
| [rc1-voice-validation.md](rc1-voice-validation.md) | Voice stack validation status |

## Changelog

Full history: [CHANGELOG.md](../../CHANGELOG.md)

## Upgrade path

- **Patch/minor:** `git pull && ./deploy.sh up`
- **Breaking changes:** documented in CHANGELOG before GA
- **Database:** `alembic upgrade head` (runs automatically in container entrypoint)
