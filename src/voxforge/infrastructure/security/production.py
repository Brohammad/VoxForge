"""Production security and configuration validation."""

from __future__ import annotations

import logging
from uuid import UUID

from voxforge.config import Settings

logger = logging.getLogger(__name__)

_INSECURE_MARKERS = ("change-me", "changeme", "replace-me", "your-secret")
_MOCK_PROVIDER_FIELDS = (
    "stt_provider",
    "llm_provider",
    "tts_provider",
    "embedding_provider",
)


def _is_insecure_secret(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _INSECURE_MARKERS)


def _mock_providers_in_use(settings: Settings) -> list[str]:
    return [name for name in _MOCK_PROVIDER_FIELDS if getattr(settings, name, "").lower() == "mock"]


def collect_production_errors(settings: Settings) -> list[str]:
    if settings.app_env != "production":
        return []

    errors: list[str] = []

    if _is_insecure_secret(settings.jwt_secret_key):
        errors.append("JWT_SECRET_KEY must be set to a strong unique value")
    if _is_insecure_secret(settings.api_key_hash_pepper):
        errors.append("API_KEY_HASH_PEPPER must be set to a strong unique value")
    if len(settings.jwt_secret_key) < 32:
        errors.append("JWT_SECRET_KEY should be at least 32 characters")

    if settings.demo_enabled:
        if not settings.demo_org_id or not settings.demo_user_id:
            errors.append("DEMO_ORG_ID and DEMO_USER_ID are required when DEMO_ENABLED=true")
        else:
            try:
                UUID(settings.demo_org_id)
                UUID(settings.demo_user_id)
            except ValueError:
                errors.append("DEMO_ORG_ID and DEMO_USER_ID must be valid UUIDs")

    if settings.stt_provider.lower() == "deepgram" and not settings.deepgram_api_key:
        errors.append("DEEPGRAM_API_KEY is required when STT_PROVIDER=deepgram")
    if settings.llm_provider.lower() == "openai" and not settings.openai_api_key:
        errors.append("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
    if settings.tts_provider.lower() == "cartesia" and not settings.cartesia_api_key:
        errors.append("CARTESIA_API_KEY is required when TTS_PROVIDER=cartesia")

    if not settings.demo_enabled:
        mocks = _mock_providers_in_use(settings)
        if mocks:
            errors.append(
                "Mock voice/embedding providers are not allowed in production "
                f"when DEMO_ENABLED=false: {', '.join(mocks)}"
            )

    if settings.trusted_hosts.strip() in ("", "*"):
        errors.append("TRUSTED_HOSTS must list your public domain(s) in production")

    if not settings.cors_origins.strip():
        errors.append("CORS_ORIGINS must be set in production for browser clients")

    if not settings.public_base_url.strip():
        errors.append("PUBLIC_BASE_URL must be set in production")

    if not settings.auth_required:
        errors.append("AUTH_REQUIRED must be true in production")

    if settings.registration_enabled and not settings.demo_enabled:
        errors.append(
            "REGISTRATION_ENABLED must be false in production when DEMO_ENABLED=false "
            "(use org invites for new users)"
        )

    if settings.handoff_enabled:
        if not settings.handoff_replay_signing_secret.strip():
            errors.append("HANDOFF_REPLAY_SIGNING_SECRET must be set when handoff is enabled")
        elif _is_insecure_secret(settings.handoff_replay_signing_secret):
            errors.append("HANDOFF_REPLAY_SIGNING_SECRET must be set to a strong unique value")
        elif settings.handoff_replay_signing_secret == settings.jwt_secret_key:
            errors.append("HANDOFF_REPLAY_SIGNING_SECRET must differ from JWT_SECRET_KEY")

    stub_providers: list[str] = []
    if settings.ticketing_provider.lower() in ("zendesk", "freshdesk"):
        stub_providers.append(f"TICKETING_PROVIDER={settings.ticketing_provider}")
    if settings.knowledge_base_provider.lower() in ("zendesk", "freshdesk"):
        stub_providers.append(f"KNOWLEDGE_BASE_PROVIDER={settings.knowledge_base_provider}")
    if stub_providers:
        errors.append(
            "Stub support integrations are not allowed in production "
            f"(use mock or internal): {', '.join(stub_providers)}"
        )

    if settings.metrics_allow_anonymous_effective:
        errors.append(
            "METRICS_ALLOW_ANONYMOUS must be false in production "
            "(set METRICS_BEARER_TOKEN or use IP allow-list)"
        )

    if settings.mcp_servers_config.strip() and settings.mcp_startup_discover:
        try:
            import mcp  # noqa: F401
        except ImportError:
            errors.append(
                "MCP_SERVERS_CONFIG is set but the mcp package is not installed; "
                "pip install -e '.[mcp]'"
            )

    return errors


def log_startup_security_warnings(settings: Settings) -> None:
    """Emit non-fatal warnings for risky but allowed development configuration."""
    if settings.registration_enabled:
        logger.warning(
            "REGISTRATION_ENABLED is true; open signup has no email verification — "
            "set REGISTRATION_ENABLED=false for invite-only access"
        )

    if settings.app_env == "production":
        return

    if _is_insecure_secret(settings.jwt_secret_key):
        logger.warning(
            "JWT_SECRET_KEY uses a development placeholder; set a strong secret before production"
        )
    if not settings.trusted_host_list:
        logger.warning("TRUSTED_HOSTS is unset; TrustedHostMiddleware is disabled")
    if not settings.cors_origin_list:
        logger.warning("CORS_ORIGINS is unset; CORSMiddleware is disabled")
    if not settings.demo_enabled:
        logger.info("DEMO_ENABLED is false; /demo quickstart and /api/v1/demo/* return 404")


def validate_production_settings(settings: Settings) -> None:
    errors = collect_production_errors(settings)
    if errors:
        raise RuntimeError("Production configuration invalid: " + "; ".join(errors))
