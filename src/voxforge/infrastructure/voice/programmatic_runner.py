from uuid import UUID

from voxforge.core.domain.entities import TurnMetrics
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.telemetry import get_tracer
from voxforge.modules.voice_gateway.application.pipeline import VoicePipelineService

logger = get_logger(__name__)
_tracer = get_tracer(__name__)


class ProgrammaticPipelineRunner:
    """Adapter that runs scripted turns through VoicePipelineService."""

    def __init__(
        self,
        pipeline: VoicePipelineService,
        *,
        bundle: object | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._bundle = bundle

    async def run_scripted_turn(
        self,
        session_id: UUID,
        org_id: UUID,
        *,
        transcript: str,
        user_metadata: dict | None = None,
    ) -> TurnMetrics:
        with _tracer.start_as_current_span("onboarding.pipeline_runner.run_scripted_turn") as span:
            span.set_attribute("voxforge.session_id", str(session_id))
            span.set_attribute("voxforge.org_id", str(org_id))
            span.set_attribute("voxforge.transcript_length", len(transcript))

            self._pipeline.set_session_org(session_id, org_id)
            if self._bundle is not None:
                await self._bundle.bootstrap_session_agent_config(org_id, session_id)
            else:
                from voxforge.core.domain.auth import ROLE_SCOPES, OrgRole

                self._pipeline.set_caller_scopes(session_id, list(ROLE_SCOPES[OrgRole.OWNER]))
            logger.info(
                "onboarding_scripted_turn_start",
                session_id=str(session_id),
                org_id=str(org_id),
            )
            metrics = await self._pipeline.run_text_turn(
                session_id,
                transcript,
                user_metadata=user_metadata,
            )
            logger.info(
                "onboarding_scripted_turn_complete",
                session_id=str(session_id),
                e2e_ms=metrics.e2e_ms,
            )
            return metrics
