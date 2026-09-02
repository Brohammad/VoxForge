import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from voxforge.config import Settings
from voxforge.core.domain.entities import MessageRole, SessionPhase, TurnMetrics
from voxforge.core.domain.events import AudioChunk, TranscriptEvent
from voxforge.core.interfaces.providers import SpeechProvider, TTSProvider
from voxforge.core.interfaces.response_generator import ResponseGenerator
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.metrics import (
    e2e_turn_latency_seconds,
    llm_first_token_seconds,
    stt_latency_seconds,
    tts_first_byte_seconds,
    turns_completed,
    turns_interrupted,
)
from voxforge.infrastructure.observability.provider_errors import record_provider_error
from voxforge.infrastructure.observability.telemetry import get_tracer
from voxforge.infrastructure.providers.tts.cartesia import token_stream_to_sentences
from voxforge.modules.session_manager.application.service import SessionManager

if TYPE_CHECKING:
    from voxforge.modules.evaluation.application.service import EvaluationEngine
    from voxforge.modules.handoff.application.orchestrator import HandoffOrchestrator
    from voxforge.modules.handoff.application.policy import HandoffPolicyEngine
    from voxforge.modules.knowledge.application.context_builder import KnowledgeContextBuilder
    from voxforge.modules.memory.application.service import MemoryService
    from voxforge.modules.outcomes.application.service import OutcomeExtractionService

logger = get_logger(__name__)
_tracer = get_tracer(__name__)


@dataclass
class PipelineCallbacks:
    on_transcript: Callable[[TranscriptEvent], Any] = field(default=lambda e: None)
    on_token: Callable[[str], Any] = field(default=lambda t: None)
    on_audio: Callable[[AudioChunk], Any] = field(default=lambda c: None)
    on_metrics: Callable[[TurnMetrics], Any] = field(default=lambda m: None)
    on_error: Callable[[str, str], Any] = field(default=lambda c, m: None)
    on_agent_step: Callable[[str, str, dict], Any] = field(default=lambda a, s, p: None)


class VoicePipelineService:
    def __init__(
        self,
        session_manager: SessionManager,
        stt_provider: SpeechProvider,
        response_generator: ResponseGenerator,
        tts_provider: TTSProvider,
        settings: Settings,
        memory_service: "MemoryService | None" = None,
        evaluation_engine: "EvaluationEngine | None" = None,
        outcome_service: "OutcomeExtractionService | None" = None,
        handoff_orchestrator: "HandoffOrchestrator | None" = None,
        handoff_policy: "HandoffPolicyEngine | None" = None,
        knowledge_context_builder: "KnowledgeContextBuilder | None" = None,
    ) -> None:
        self._sessions = session_manager
        self._stt = stt_provider
        self._response_generator = response_generator
        self._tts = tts_provider
        self._settings = settings
        self._memory = memory_service
        self._evaluation = evaluation_engine
        self._outcomes = outcome_service
        self._handoff = handoff_orchestrator
        self._handoff_policy = handoff_policy
        self._knowledge_context = knowledge_context_builder
        self._session_orgs: dict[UUID, UUID] = {}
        self._interrupt_event: asyncio.Event | None = None
        self._pipeline_task: asyncio.Task | None = None

    def set_response_generator(self, response_generator: ResponseGenerator) -> None:
        self._response_generator = response_generator

    def set_session_org(self, session_id: UUID, org_id: UUID | None) -> None:
        if org_id is not None:
            self._session_orgs[session_id] = org_id
        self._response_generator.set_session_org(session_id, org_id)

    def set_caller_scopes(self, session_id: UUID, scopes: list[str]) -> None:
        setter = getattr(self._response_generator, "set_caller_scopes", None)
        if callable(setter):
            setter(session_id, scopes)

    async def run_listening(
        self,
        session_id: UUID,
        audio_queue: asyncio.Queue[bytes | None],
        callbacks: PipelineCallbacks,
        *,
        language: str | None = None,
    ) -> None:
        """Listen for audio, transcribe, and process complete utterances."""

        async def audio_stream() -> AsyncIterator[bytes]:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                yield chunk

        self._interrupt_event = asyncio.Event()
        turn_start = time.monotonic()
        first_partial_time: float | None = None

        with _tracer.start_as_current_span("voice_pipeline.run_listening") as span:
            span.set_attribute("voxforge.session_id", str(session_id))
            try:
                async for event in self._stt.transcribe_stream(audio_stream(), language=language):
                    if self._interrupt_event and self._interrupt_event.is_set():
                        break

                    if event.is_partial:
                        if first_partial_time is None:
                            first_partial_time = time.monotonic()
                            stt_latency_seconds.observe(first_partial_time - turn_start)
                        await self._maybe_await(callbacks.on_transcript(event))
                    else:
                        await self._maybe_await(callbacks.on_transcript(event))
                        final_transcript = event.text.strip()
                        if final_transcript:
                            await self._process_turn(
                                session_id,
                                final_transcript,
                                callbacks,
                                turn_start=turn_start,
                                stt_ms=(first_partial_time - turn_start) * 1000
                                if first_partial_time
                                else None,
                                confidence=event.confidence,
                            )
                        turn_start = time.monotonic()
                        first_partial_time = None
            except asyncio.CancelledError:
                logger.info("pipeline_listening_cancelled", session_id=str(session_id))
                raise
            except Exception as exc:
                span.record_exception(exc)
                record_provider_error(self._settings.stt_provider, "transcribe_stream")
                logger.error("pipeline_listening_error", session_id=str(session_id), error=str(exc))
                await self._maybe_await(
                    callbacks.on_error("pipeline_error", "Voice pipeline failed")
                )

    async def run_text_turn(
        self,
        session_id: UUID,
        transcript: str,
        callbacks: PipelineCallbacks | None = None,
        *,
        user_metadata: dict | None = None,
        confidence: float | None = 1.0,
    ) -> TurnMetrics:
        """Run a single turn from text input, skipping STT (programmatic / onboarding)."""
        effective_callbacks = callbacks or PipelineCallbacks()
        turn_start = time.monotonic()

        with _tracer.start_as_current_span("voice_pipeline.run_text_turn") as span:
            span.set_attribute("voxforge.session_id", str(session_id))
            span.set_attribute("voxforge.transcript_length", len(transcript))
            span.set_attribute("voxforge.mode", "programmatic")
            try:
                metrics = await self._process_turn(
                    session_id,
                    transcript,
                    effective_callbacks,
                    turn_start=turn_start,
                    stt_ms=0.0,
                    confidence=confidence,
                    user_metadata_extra=user_metadata,
                )
                logger.info(
                    "pipeline_text_turn_completed",
                    session_id=str(session_id),
                    e2e_ms=metrics.e2e_ms,
                )
                return metrics
            except Exception as exc:
                span.record_exception(exc)
                logger.error(
                    "pipeline_text_turn_failed",
                    session_id=str(session_id),
                    error=str(exc),
                )
                raise

    async def _process_turn(
        self,
        session_id: UUID,
        transcript: str,
        callbacks: PipelineCallbacks,
        *,
        turn_start: float,
        stt_ms: float | None,
        confidence: float | None,
        user_metadata_extra: dict | None = None,
    ) -> TurnMetrics:
        metrics = TurnMetrics(stt_ms=stt_ms)
        self._interrupt_event = asyncio.Event()

        await self._sessions.update_phase(session_id, SessionPhase.PROCESSING)
        user_metadata: dict = {"confidence": confidence}
        if user_metadata_extra:
            user_metadata.update(user_metadata_extra)
        user_message = await self._sessions.save_user_message(
            session_id, transcript, metadata=user_metadata
        )
        org_id = self._session_orgs.get(session_id)
        if self._memory and org_id is not None:
            await self._memory.store_turn(
                org_id=org_id,
                session_id=session_id,
                role=MessageRole.USER.value,
                content=transcript,
                message_id=user_message.id,
                metadata={"confidence": confidence},
            )
        self._response_generator.add_user_message(session_id, transcript)

        assistant_text = ""
        llm_start = time.monotonic()
        first_token_time: float | None = None
        first_audio_time: float | None = None
        was_interrupted = False

        async def on_agent_step(agent: str, status: str, payload: dict) -> None:
            await self._maybe_await(callbacks.on_agent_step(agent, status, payload))

        async def token_iter() -> AsyncIterator[str]:
            nonlocal assistant_text, first_token_time, was_interrupted
            async for event in self._response_generator.generate_response(
                session_id,
                on_agent_step=on_agent_step,
            ):
                if self._interrupt_event and self._interrupt_event.is_set():
                    was_interrupted = True
                    break
                if event.text:
                    if first_token_time is None:
                        first_token_time = time.monotonic()
                        metrics.llm_first_token_ms = (first_token_time - llm_start) * 1000
                        llm_first_token_seconds.observe(first_token_time - llm_start)
                    assistant_text += event.text
                    await self._maybe_await(callbacks.on_token(event.text))
                    yield event.text

        await self._sessions.update_phase(session_id, SessionPhase.SPEAKING)

        config = await self._sessions.get_session_config(session_id)
        voice_id = config.get("voice_id", self._settings.default_tts_voice_id)

        try:
            async for sentence in token_stream_to_sentences(token_iter()):
                if self._interrupt_event and self._interrupt_event.is_set():
                    was_interrupted = True
                    turns_interrupted.inc()
                    break

                text_to_speak = sentence

                async def single_text(text=text_to_speak) -> AsyncIterator[str]:
                    yield text

                async for chunk in self._tts.synthesize_stream(single_text(), voice_id=voice_id):
                    if self._interrupt_event and self._interrupt_event.is_set():
                        was_interrupted = True
                        turns_interrupted.inc()
                        break
                    if first_audio_time is None:
                        first_audio_time = time.monotonic()
                        metrics.tts_first_byte_ms = (first_audio_time - llm_start) * 1000
                        metrics.e2e_ms = (first_audio_time - turn_start) * 1000
                        tts_first_byte_seconds.observe(first_audio_time - llm_start)
                        e2e_turn_latency_seconds.observe(first_audio_time - turn_start)
                    await self._maybe_await(callbacks.on_audio(chunk))
        except Exception as exc:
            record_provider_error(self._settings.tts_provider, "synthesize_stream")
            logger.error("pipeline_tts_error", session_id=str(session_id), error=str(exc))
            await self._maybe_await(callbacks.on_error("tts_error", "Speech synthesis failed"))

        if assistant_text:
            trace = self._response_generator.get_last_agent_trace(session_id)
            assistant_metadata: dict[str, Any] = {"agent_trace": trace} if trace else {}
            self._response_generator.add_assistant_message(session_id, assistant_text)
            assistant_message = await self._sessions.save_assistant_message(
                session_id, assistant_text, metadata=assistant_metadata
            )
            if self._memory and org_id is not None:
                await self._memory.store_turn(
                    org_id=org_id,
                    session_id=session_id,
                    role=MessageRole.ASSISTANT.value,
                    content=assistant_text,
                    message_id=assistant_message.id,
                    metadata=assistant_metadata,
                )
        else:
            assistant_metadata = {}

        await self._sessions.save_turn_metrics(session_id, metrics)
        evaluation_run = None
        if self._evaluation:
            from voxforge.core.domain.evaluation import TurnEvaluationInput

            trace = self._response_generator.get_last_agent_trace(session_id)
            tool_calls = [
                {"status": step.get("status", ""), "tool": step.get("agent")}
                for step in trace
                if step.get("agent") == "tool"
            ]
            context_snippets: list[str] = []
            if self._memory and org_id is not None:
                memory_ctx = await self._memory.retrieve_context(
                    org_id=org_id,
                    session_id=session_id,
                    query=transcript,
                )
                if memory_ctx.summary:
                    context_snippets.append(memory_ctx.summary)
                context_snippets.extend(e.content for e in memory_ctx.relevant_entries)
            if (
                self._knowledge_context
                and org_id is not None
                and self._settings.knowledge_context_enabled
            ):
                kb_snippets = await self._knowledge_context.retrieve_snippets(
                    org_id=org_id,
                    query=transcript,
                )
                context_snippets.extend(kb_snippets)
            evaluation_run = await self._evaluation.evaluate_turn(
                TurnEvaluationInput(
                    session_id=session_id,
                    org_id=org_id,
                    user_transcript=transcript,
                    assistant_response=assistant_text,
                    stt_ms=metrics.stt_ms,
                    llm_first_token_ms=metrics.llm_first_token_ms,
                    tts_first_byte_ms=metrics.tts_first_byte_ms,
                    e2e_ms=metrics.e2e_ms,
                    tool_calls=tool_calls,
                    interrupted=was_interrupted,
                    context_snippets=context_snippets,
                )
            )

        if (
            self._handoff
            and self._handoff_policy
            and org_id is not None
            and self._settings.handoff_enabled
        ):
            from voxforge.infrastructure.observability.metrics import (
                handoff_confidence_at_escalation,
            )
            from voxforge.modules.handoff.application.context import build_turn_handoff_context
            from voxforge.modules.handoff.application.policy_loader import load_escalation_policy

            trace = self._response_generator.get_last_agent_trace(session_id)
            config = await self._sessions.get_session_config(session_id)
            policy = load_escalation_policy(config, self._settings)
            tool_failures = sum(
                1
                for step in (trace or [])
                if step.get("agent") == "tool"
                and str(step.get("status", "")).lower() in ("error", "timeout", "failed")
            )
            consecutive = await self._sessions.track_tool_failures(session_id, tool_failures)
            handoff_ctx = build_turn_handoff_context(
                user_transcript=transcript,
                assistant_response=assistant_text,
                interrupted=was_interrupted,
                confidence=confidence,
                agent_trace=trace,
                evaluation_run=evaluation_run,
                consecutive_tool_failures=consecutive,
            )
            decision = self._handoff_policy.evaluate(handoff_ctx, policy)
            if decision.should_escalate and decision.trigger is not None:
                if decision.confidence is not None:
                    handoff_confidence_at_escalation.labels(trigger=decision.trigger.value).observe(
                        decision.confidence
                    )
                package = await self._handoff.initiate_handoff(
                    org_id=org_id,
                    session_id=session_id,
                    trigger=decision.trigger,
                    reason=decision.reason,
                    confidence_score=decision.confidence,
                    policy=policy,
                )
                assistant_metadata["escalation"] = True
                assistant_metadata["handoff_id"] = str(package.handoff_id)
                assistant_metadata["ticket_id"] = package.ticket_id

        if self._outcomes:
            await self._outcomes.record_outcome(
                org_id=org_id,
                session_id=session_id,
                user_transcript=transcript,
                assistant_response=assistant_text,
                interrupted=was_interrupted,
                resolution_time_seconds=(
                    metrics.e2e_ms / 1000 if metrics.e2e_ms is not None else None
                ),
                user_metadata=user_metadata,
                assistant_metadata=assistant_metadata,
            )
        await self._sessions.commit()
        await self._maybe_await(callbacks.on_metrics(metrics))
        turns_completed.inc()

        await self._sessions.clear_interrupt(session_id)
        await self._sessions.update_phase(session_id, SessionPhase.LISTENING)
        return metrics

    async def interrupt(self, session_id: UUID) -> None:
        await self._sessions.set_interrupt(session_id)
        if self._interrupt_event:
            self._interrupt_event.set()
        logger.info("pipeline_interrupted", session_id=str(session_id))

    @staticmethod
    async def _maybe_await(result: Any) -> None:
        if asyncio.iscoroutine(result):
            await result
