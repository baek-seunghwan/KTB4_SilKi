"""Authenticated WebSocket session orchestration for streaming speech."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
from collections import deque
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from silki_ai.clova import ClovaEvent, ClovaEventKind
from silki_ai.contracts import (
    CLIENT_MESSAGE_ADAPTER,
    CartContext,
    DialogAction,
    DialogChoice,
    DialogClarification,
    DialogCompleted,
    DialogListen,
    DialogProposal,
    DialogReject,
    DialogReset,
    ErrorCode,
    ErrorMessage,
    MenuCandidates,
    NoMatch,
    SessionEnd,
    SessionReady,
    SessionStart,
    SttPartial,
    TtsAudio,
    TtsUnavailable,
    TurnEndReason,
    TurnFinal,
    TurnStarted,
)
from silki_ai.dialog import (
    DialogActionDecision,
    DialogClarificationDecision,
    DialogCompletedDecision,
    DialogNotReadyError,
    DialogPhase,
    DialogProposalDecision,
    DialogSearchRequest,
    StaleDialogError,
    VoiceOrderDialogAgent,
)
from silki_ai.security import TokenValidationError
from silki_ai.turn_manager import TurnEvent, TurnEventType, TurnManager
from silki_ai.ws_transport import WebSocketSender

logger = logging.getLogger(__name__)
router = APIRouter(tags=["streaming"])


def _uuid(value: str) -> UUID:
    return UUID(value)


def clova_public_error_message(provider_error: str | None) -> str:
    """Return an actionable message without exposing provider internals or credentials."""

    normalized = (provider_error or "").lower()
    if "unauthenticated" in normalized or "invalid authentication token" in normalized:
        return "CLOVA Speech Secret Key가 올바르지 않거나 실시간 스트리밍 권한이 없습니다."
    if "no more slot" in normalized or "resource_exhausted" in normalized:
        return "CLOVA Speech 동시 연결 한도가 찼습니다. 잠시 후 다시 시도해주세요."
    return "CLOVA Speech 스트리밍 연결에 실패했습니다."


class VoiceSession:
    """Coordinate one WebSocket, one CLOVA stream, and multiple user turns."""

    def __init__(
        self,
        *,
        websocket: WebSocket,
        container: Any,
        session_id: UUID,
        order_session_id: str,
        store_id: str,
        session_start: SessionStart,
        speech: Any,
    ) -> None:
        self.websocket = websocket
        self.container = container
        self.settings = container.settings
        self.sender = WebSocketSender(websocket)
        self.session_id = session_id
        self.order_session_id = order_session_id
        self.store_id = store_id
        self.speech = speech
        self.vad = container.create_vad()
        self.turns = TurnManager(
            sample_rate_hz=self.settings.audio_sample_rate_hz,
            channels=self.settings.audio_channels,
            sample_width_bytes=self.settings.audio_sample_width_bytes,
            frame_duration_ms=self.settings.audio_frame_duration_ms,
            silence_seconds=self.settings.turn_silence_seconds,
            incomplete_silence_seconds=self.settings.turn_incomplete_silence_seconds,
            max_turn_seconds=self.settings.turn_max_seconds,
            transcript_stable_seconds=self.settings.turn_transcript_stable_seconds,
            min_rms_dbfs=self.settings.vad_min_rms_dbfs,
        )
        self.based_on_cart_version = session_start.based_on_cart_version
        self.cart_items = tuple(session_start.cart_items)
        self.dialog_capabilities = list(session_start.capabilities)
        self.dialog = VoiceOrderDialogAgent() if "dialog.v1" in session_start.capabilities else None
        self._dialog_lock = asyncio.Lock()
        self._dialog_task: asyncio.Task[None] | None = None
        self._dialog_turn_id: str | None = None
        self._dialog_based_on_cart_version = self.based_on_cart_version
        self._turn_versions: dict[str, int] = {}
        self._speech_turns: dict[int, str] = {}
        self._audio_buffer = bytearray()
        # Audio captured while the VAD/energy gate was still closed. The gate
        # only opens once the utterance is loud enough, so without replaying
        # these frames CLOVA never hears the onset of the first word.
        # ``maxlen=0`` keeps the deque permanently empty, so a zero pre-roll
        # setting disables the replay without a second branch below.
        self._preroll: deque[bytes] = deque(maxlen=self.settings.preroll_frame_count)
        self._search_tasks: set[asyncio.Task[None]] = set()
        self._speech_listener: asyncio.Task[None] | None = None
        self._closing = False

    async def run(self) -> None:
        should_close_normally = False
        try:
            await self.speech.start()
            await self.sender.send_model(
                SessionReady(
                    session_id=self.session_id,
                    order_session_id=self.order_session_id,
                    store_id=self.store_id,
                    capabilities=self.dialog_capabilities,
                )
            )
            self._speech_listener = asyncio.create_task(
                self._consume_speech_events(), name=f"clova-{self.session_id}"
            )
            while not self._closing:
                message = await asyncio.wait_for(
                    self.websocket.receive(),
                    timeout=self.settings.websocket_idle_timeout_seconds,
                )
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await self._handle_audio(message["bytes"])
                elif message.get("text") is not None:
                    if await self._handle_control(message["text"]):
                        break
            should_close_normally = True
        except (TimeoutError, WebSocketDisconnect):
            should_close_normally = True
        finally:
            self._closing = True
            if self._speech_listener is not None:
                self._speech_listener.cancel()
                await asyncio.gather(self._speech_listener, return_exceptions=True)
            search_tasks = tuple(self._search_tasks)
            for task in search_tasks:
                task.cancel()
            if search_tasks:
                await asyncio.gather(*search_tasks, return_exceptions=True)
            await self.speech.close()
            if should_close_normally:
                with contextlib.suppress(Exception):
                    await self.websocket.close(code=1000)

    async def _handle_audio(self, chunk: bytes) -> None:
        # dialog.v1 explicitly opens input with dialog.listen.  Dropping frames
        # while processing/TTS/confirmation prevents buffered audio and the
        # synthesized prompt itself from becoming a new CLOVA turn.
        if self.dialog is not None and self.dialog.phase is not DialogPhase.LISTENING:
            return
        if not chunk or len(chunk) % self.settings.audio_sample_width_bytes:
            await self._error(
                ErrorCode.AUDIO_FORMAT_INVALID,
                "PCM audio must contain complete signed 16-bit samples",
                retryable=True,
                turn_id=self.turns.active_turn_id,
            )
            return
        if len(chunk) > 1024 * 1024:
            await self._error(
                ErrorCode.AUDIO_FORMAT_INVALID,
                "audio frame is too large",
                retryable=True,
                turn_id=self.turns.active_turn_id,
            )
            return

        self._audio_buffer.extend(chunk)
        frame_bytes = self.turns.frame_bytes
        while len(self._audio_buffer) >= frame_bytes:
            if self.dialog is not None and self.dialog.phase is not DialogPhase.LISTENING:
                self._audio_buffer.clear()
                # Never let audio from a non-listening phase (the assistant's
                # own TTS prompt, most of all) survive as the next turn's onset.
                self._preroll.clear()
                break
            frame = bytes(self._audio_buffer[:frame_bytes])
            del self._audio_buffer[:frame_bytes]
            active_before = self.turns.active_turn_id is not None
            try:
                voiced = bool(self.vad.is_speech(frame, self.settings.audio_sample_rate_hz))
            except Exception:
                voiced = None
            events = self.turns.process_frame(frame, voiced=voiced)
            active_after = self.turns.active_turn_id is not None
            for event in events:
                if event.type is TurnEventType.STARTED:
                    # Establish correlation before CLOVA can emit a partial.
                    await self._turn_started(event)
            if active_before or active_after:
                if not active_before:
                    # Replay the onset the gate swallowed, in capture order and
                    # one frame at a time, so CLOVA sees a continuous stream.
                    for buffered_frame in self._preroll:
                        await self.speech.send_audio(buffered_frame)
                    logger.info(
                        "turn %s starts with %d pre-roll frames (%d ms)",
                        self.turns.active_turn_id,
                        len(self._preroll),
                        len(self._preroll) * self.turns.frame_duration_ms,
                    )
                    self._preroll.clear()
                await self.speech.send_audio(frame)
            else:
                self._preroll.append(frame)
            for event in events:
                if event.type is TurnEventType.FINALIZE:
                    await self._finalize_turn(event)

    async def _handle_control(self, raw: str) -> bool:
        try:
            message = CLIENT_MESSAGE_ADAPTER.validate_json(raw)
        except (ValidationError, ValueError, json.JSONDecodeError):
            await self._error(
                ErrorCode.PROTOCOL_ERROR,
                "invalid client control message",
                retryable=True,
            )
            return False

        if isinstance(message, SessionStart):
            await self._error(
                ErrorCode.PROTOCOL_ERROR,
                "session.start may only be sent once",
                retryable=False,
            )
            return False
        if message.session_id != self.session_id:
            await self._error(
                ErrorCode.PROTOCOL_ERROR,
                "sessionId does not match this WebSocket session",
                retryable=False,
            )
            return False
        if isinstance(message, CartContext):
            if message.based_on_cart_version < self.based_on_cart_version:
                await self._error(
                    ErrorCode.STALE_CART_CONTEXT,
                    "basedOnCartVersion must not move backwards",
                    retryable=True,
                    turn_id=self.turns.active_turn_id,
                )
                return False
            previous_version = self.based_on_cart_version
            self.based_on_cart_version = message.based_on_cart_version
            self.cart_items = tuple(message.cart_items)
            if self.dialog is not None and message.based_on_cart_version > previous_version:
                completed: DialogCompletedDecision | None = None
                if self.dialog.can_complete_cart:
                    # The FE may open confirmation voice input before the user
                    # presses the visible accept button.  cart_completed()
                    # accepts that authoritative result only for the active
                    # proposal (including a pending spoken accept action).
                    was_listening = self.dialog.phase is DialogPhase.LISTENING
                    with contextlib.suppress(DialogNotReadyError):
                        completed = self.dialog.cart_completed()
                    if completed is not None and was_listening:
                        await self._discard_dialog_audio_turn()
                if completed is not None:
                    await self._send_dialog_completed(completed)
                elif self.dialog.phase is DialogPhase.PROCESSING:
                    if self._dialog_task is not None:
                        self._dialog_task.cancel()
                    # The cart changed underneath an in-flight interpretation.
                    # Start a fresh bounded conversation and discard its late result.
                    self.dialog = VoiceOrderDialogAgent()
                    self._dialog_turn_id = None
            return False
        if isinstance(message, (DialogListen, DialogChoice, DialogReject, DialogReset)):
            await self._handle_dialog_control(message)
            return False
        if isinstance(message, SessionEnd):
            final = self.turns.force_finalize("session_end")
            if final is not None:
                await self._finalize_turn(final)
            return True
        return False

    async def _handle_dialog_control(
        self,
        message: DialogListen | DialogChoice | DialogReject | DialogReset,
    ) -> None:
        if self.dialog is None:
            await self._error(
                ErrorCode.PROTOCOL_ERROR,
                "dialog controls require the dialog.v1 capability",
                retryable=False,
            )
            return
        try:
            if isinstance(message, DialogListen):
                self.dialog.listen(
                    conversation_id=message.conversation_id,
                    dialog_id=message.dialog_id,
                    revision=message.revision,
                )
                self._audio_buffer.clear()
                self._preroll.clear()
                return
            if isinstance(message, DialogChoice):
                was_listening = self.dialog.phase is DialogPhase.LISTENING
                outcome = self.dialog.choose(
                    conversation_id=message.conversation_id,
                    dialog_id=message.dialog_id,
                    revision=message.revision,
                    choice_id=message.choice_id,
                    value=message.value,
                    label=message.label,
                )
                if was_listening:
                    # A visible choice remains valid after automatic voice input
                    # opens. Prefer the validated button selection and discard
                    # any partial/noise-only audio from that listening window.
                    await self._discard_dialog_audio_turn()
                await self._handle_dialog_outcome(outcome)
                return
            if isinstance(message, DialogReject):
                was_listening = self.dialog.phase is DialogPhase.LISTENING
                decision = self.dialog.reject(
                    conversation_id=message.conversation_id,
                    dialog_id=message.dialog_id,
                    revision=message.revision,
                )
                if was_listening:
                    await self._discard_dialog_audio_turn()
                await self._send_dialog_decision(decision)
                return
            was_listening = self.dialog.phase is DialogPhase.LISTENING
            decision = self.dialog.reset(
                conversation_id=message.conversation_id,
                dialog_id=message.dialog_id,
                revision=message.revision,
            )
            if was_listening:
                await self._discard_dialog_audio_turn()
            await self._send_dialog_decision(decision)
        except StaleDialogError:
            await self._error(
                ErrorCode.STALE_DIALOG,
                "dialog control does not match the current prompt",
                retryable=True,
                turn_id=self._dialog_turn_id,
            )
        except DialogNotReadyError:
            await self._error(
                ErrorCode.DIALOG_NOT_READY,
                "dialog control is not allowed in the current state",
                retryable=True,
                turn_id=self._dialog_turn_id,
            )

    async def _discard_dialog_audio_turn(self) -> None:
        """Discard one superseded dialog listening window atomically.

        Visible controls and an authoritative cart update are allowed to win
        over voice input that is still in progress.  Reset every local
        correlation/buffer and replace the CLOVA stream so a late partial or
        flush from that abandoned turn cannot finalize into the next prompt.
        """

        self.turns.reset()
        self._audio_buffer.clear()
        self._preroll.clear()
        self._turn_versions.clear()
        await self._replace_speech_client()

    async def _replace_speech_client(self) -> None:
        """Start a clean CLOVA stream for the next independently bounded turn.

        CLOVA may accept PCM after an epFlag flush without publishing another
        transcript on the same gRPC stream. Reopening only the provider stream
        keeps the authenticated browser WebSocket and dialog state intact.
        """

        listener = self._speech_listener
        self._speech_listener = None
        if listener is not None:
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
        await self.speech.close()
        self.speech = self.container.create_speech_client()
        await self.speech.start()
        self._speech_turns.clear()
        self._preroll.clear()
        self._speech_listener = asyncio.create_task(
            self._consume_speech_events(),
            name=f"clova-{self.session_id}",
        )

    async def _turn_started(self, event: TurnEvent) -> None:
        self._turn_versions[event.turn_id] = self.based_on_cart_version
        generation = int(getattr(self.speech, "generation", 0))
        self._speech_turns[generation] = event.turn_id
        await self.sender.send_model(
            TurnStarted(
                session_id=self.session_id,
                turn_id=_uuid(event.turn_id),
                based_on_cart_version=self.based_on_cart_version,
            )
        )

    async def _consume_speech_events(self) -> None:
        async for event in self.speech.events():
            turn_id = self._speech_turns.get(event.generation)
            if event.kind is ClovaEventKind.ERROR:
                turn_id = turn_id or self.turns.active_turn_id
                public_message = clova_public_error_message(event.error)
                logger.warning("CLOVA stream unavailable: %s", public_message)
                await self._error(
                    ErrorCode.CLOVA_UNAVAILABLE,
                    public_message,
                    retryable=True,
                    turn_id=turn_id,
                )
                self._closing = True
                with contextlib.suppress(Exception):
                    await self.websocket.close(code=1011)
                return
            if turn_id is None or not event.text.strip():
                continue
            self.turns.on_stt_result(
                event.text,
                semantic_epd=event.epd_type is not None,
            )
            await self.sender.send_model(
                SttPartial(
                    session_id=self.session_id,
                    turn_id=_uuid(turn_id),
                    text=event.text,
                )
            )

    async def _finalize_turn(self, event: TurnEvent) -> None:
        turn_id = event.turn_id
        flush_failed = False
        try:
            final_event: ClovaEvent = await self.speech.flush(
                timeout_seconds=self.settings.clova_flush_timeout_seconds
            )
            text = final_event.text.strip() or self.turns.transcript.strip()
        except Exception:
            flush_failed = True
            text = self.turns.transcript.strip()
            await self._error(
                ErrorCode.CLOVA_UNAVAILABLE,
                "unable to finalize speech transcription",
                retryable=True,
                turn_id=turn_id,
            )

        reason = (
            TurnEndReason.SESSION_END
            if event.reason == "session_end"
            else TurnEndReason.MAX_DURATION
            if event.reason == "max_duration"
            else TurnEndReason.INCOMPLETE_TIMEOUT
            if event.reason == "incomplete_timeout"
            else TurnEndReason.TRANSCRIPT_STABLE_TIMEOUT
            if event.reason == "transcript_stable_timeout"
            else TurnEndReason.SILENCE
        )
        if text:
            await self.sender.send_model(
                TurnFinal(
                    session_id=self.session_id,
                    turn_id=_uuid(turn_id),
                    text=text,
                    reason=reason,
                )
            )

        self.speech.reset_transcript()
        self.turns.complete_turn(turn_id)
        # Frames streamed while the turn was finalizing already reached CLOVA;
        # they must not be replayed as the next turn's pre-roll.
        self._preroll.clear()
        for generation, mapped_turn_id in tuple(self._speech_turns.items()):
            if mapped_turn_id == turn_id:
                self._speech_turns.pop(generation, None)

        if flush_failed:
            # Partial responses cannot be safely correlated after a failed
            # seqId barrier. Force a fresh WebSocket/CLOVA session instead of
            # risking cross-turn transcript contamination.
            self._closing = True
            with contextlib.suppress(Exception):
                await self.websocket.close(code=1011)
            return

        dialog_based_on_version: int | None = None
        if self.dialog is not None:
            dialog_based_on_version = self._turn_versions.pop(
                turn_id,
                self.based_on_cart_version,
            )
            if event.reason != "session_end" and not self._closing:
                await self._replace_speech_client()

        if text and not self._closing:
            if self.dialog is None:
                task = asyncio.create_task(
                    self._recommend(turn_id, text), name=f"recommend-{turn_id}"
                )
                self._search_tasks.add(task)
                task.add_done_callback(self._search_tasks.discard)
            else:
                based_on_version = (
                    dialog_based_on_version
                    if dialog_based_on_version is not None
                    else self.based_on_cart_version
                )
                try:
                    outcome = self.dialog.begin_turn(text)
                except DialogNotReadyError:
                    await self._error(
                        ErrorCode.DIALOG_NOT_READY,
                        "dialog is not ready for another speech turn",
                        retryable=True,
                        turn_id=turn_id,
                    )
                    return
                self._dialog_turn_id = turn_id
                self._dialog_based_on_cart_version = based_on_version
                await self._handle_dialog_outcome(outcome)

    def _schedule_dialog_search(
        self,
        request: DialogSearchRequest,
        turn_id: str,
        based_on_version: int,
    ) -> None:
        task = asyncio.create_task(
            self._process_dialog_search(request, turn_id, based_on_version),
            name=f"dialog-{turn_id}-{request.revision}",
        )
        self._dialog_task = task
        self._search_tasks.add(task)

        def discard(completed: asyncio.Task[None]) -> None:
            self._search_tasks.discard(completed)
            if self._dialog_task is completed:
                self._dialog_task = None

        task.add_done_callback(discard)

    async def _process_dialog_search(
        self,
        request: DialogSearchRequest,
        turn_id: str,
        based_on_version: int,
    ) -> None:
        agent = self.dialog
        if agent is None:
            return
        try:
            async with self._dialog_lock:
                if (
                    self.dialog is not agent
                    or agent.phase is not DialogPhase.PROCESSING
                    or agent.conversation_id != request.conversation_id
                    or agent.revision != request.revision
                ):
                    return
                result = await self.container.recommendation_service.recommend(
                    store_id=self.store_id,
                    transcript=request.search_text,
                )
                if (
                    self._closing
                    or self.dialog is not agent
                    or self.based_on_cart_version != based_on_version
                    or agent.phase is not DialogPhase.PROCESSING
                    or agent.conversation_id != request.conversation_id
                    or agent.revision != request.revision
                ):
                    return
                decision = agent.resolve(result)
                self._dialog_turn_id = turn_id
                self._dialog_based_on_cart_version = based_on_version
                await self._send_dialog_decision(decision)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("dialog recommendation failed", extra={"turn_id": turn_id})
            await self._error(
                ErrorCode.INTERNAL_ERROR,
                "dialog recommendation failed",
                retryable=True,
                turn_id=turn_id,
            )

    async def _handle_dialog_outcome(
        self,
        outcome: DialogSearchRequest
        | DialogClarificationDecision
        | DialogProposalDecision
        | DialogCompletedDecision
        | DialogActionDecision,
    ) -> None:
        if isinstance(outcome, DialogSearchRequest):
            if self._dialog_turn_id is None:
                raise DialogNotReadyError("dialog has no correlated speech turn")
            self._schedule_dialog_search(
                outcome,
                self._dialog_turn_id,
                self.based_on_cart_version,
            )
            return
        if isinstance(outcome, DialogCompletedDecision):
            await self._send_dialog_completed(outcome)
            return
        if isinstance(outcome, DialogActionDecision):
            await self._send_dialog_action(outcome)
            return
        await self._send_dialog_decision(outcome)

    async def _send_dialog_decision(
        self,
        decision: DialogClarificationDecision | DialogProposalDecision,
    ) -> None:
        if self._dialog_turn_id is None:
            raise DialogNotReadyError("dialog decision has no correlated speech turn")
        turn_id = _uuid(self._dialog_turn_id)
        tts_expected = getattr(self.container, "tts_client", None) is not None
        if isinstance(decision, DialogClarificationDecision):
            await self.sender.send_model(
                DialogClarification(
                    session_id=self.session_id,
                    conversation_id=decision.conversation_id,
                    dialog_id=decision.dialog_id,
                    revision=decision.revision,
                    turn_id=turn_id,
                    based_on_cart_version=self._dialog_based_on_cart_version,
                    text=decision.text,
                    missing_slot=decision.missing_slot,
                    choices=list(decision.choices),
                    accumulated_slots=decision.accumulated_slots,
                    tts_expected=tts_expected,
                )
            )
            purpose = "clarification"
        else:
            await self.sender.send_model(
                DialogProposal(
                    session_id=self.session_id,
                    conversation_id=decision.conversation_id,
                    dialog_id=decision.dialog_id,
                    revision=decision.revision,
                    turn_id=turn_id,
                    based_on_cart_version=self._dialog_based_on_cart_version,
                    text=decision.text,
                    menu=decision.menu,
                    quantity=decision.quantity,
                    attributes=decision.attributes,
                    resolved_options=list(decision.resolved_options),
                    degraded=decision.degraded,
                    tts_expected=tts_expected,
                )
            )
            purpose = "proposal"
        if tts_expected:
            self._schedule_dialog_tts(decision, purpose, turn_id)
        else:
            # Make the no-provider path deterministic: FE always receives the
            # terminal TTS signal before it can open input with dialog.listen.
            await self._send_tts_unavailable(decision, purpose, turn_id)

    async def _send_dialog_completed(self, decision: DialogCompletedDecision) -> None:
        if self._dialog_turn_id is None:
            raise DialogNotReadyError("dialog completion has no correlated speech turn")
        turn_id = _uuid(self._dialog_turn_id)
        tts_expected = getattr(self.container, "tts_client", None) is not None
        await self.sender.send_model(
            DialogCompleted(
                session_id=self.session_id,
                conversation_id=decision.conversation_id,
                dialog_id=decision.dialog_id,
                revision=decision.revision,
                turn_id=turn_id,
                text=decision.text,
                tts_expected=tts_expected,
            )
        )
        if tts_expected:
            self._schedule_dialog_tts(decision, "completion", turn_id)
        else:
            await self._send_tts_unavailable(decision, "completion", turn_id)

    async def _send_dialog_action(self, decision: DialogActionDecision) -> None:
        if self._dialog_turn_id is None:
            raise DialogNotReadyError("dialog action has no correlated speech turn")
        await self.sender.send_model(
            DialogAction(
                session_id=self.session_id,
                conversation_id=decision.conversation_id,
                dialog_id=decision.dialog_id,
                revision=decision.revision,
                turn_id=_uuid(self._dialog_turn_id),
                action=decision.action,
            )
        )

    def _schedule_dialog_tts(
        self,
        decision: (DialogClarificationDecision | DialogProposalDecision | DialogCompletedDecision),
        purpose: str,
        turn_id: UUID,
    ) -> None:
        task = asyncio.create_task(
            self._send_dialog_tts(decision, purpose, turn_id),
            name=f"dialog-tts-{decision.dialog_id}",
        )
        self._search_tasks.add(task)
        task.add_done_callback(self._search_tasks.discard)

    async def _send_dialog_tts(
        self,
        decision: (DialogClarificationDecision | DialogProposalDecision | DialogCompletedDecision),
        purpose: str,
        turn_id: UUID,
    ) -> None:
        tts_client = getattr(self.container, "tts_client", None)
        if tts_client is None:
            await self._send_tts_unavailable(decision, purpose, turn_id)
            return
        try:
            audio = await tts_client.synthesize(decision.text[:500])
            if not self._dialog_is_current(decision):
                return
            await self.sender.send_model(
                TtsAudio(
                    session_id=self.session_id,
                    turn_id=turn_id,
                    media_type=audio.media_type,
                    audio_base64=base64.b64encode(audio.content).decode("ascii"),
                    text=decision.text,
                    conversation_id=decision.conversation_id,
                    dialog_id=decision.dialog_id,
                    revision=decision.revision,
                    purpose=purpose,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "TTS provider failed for dialog prompt",
                exc_info=True,
                extra={"dialog_id": str(decision.dialog_id)},
            )
            if self._dialog_is_current(decision):
                await self._send_tts_unavailable(decision, purpose, turn_id)

    async def _send_tts_unavailable(
        self,
        decision: (DialogClarificationDecision | DialogProposalDecision | DialogCompletedDecision),
        purpose: str,
        turn_id: UUID,
    ) -> None:
        if not self._dialog_is_current(decision):
            return
        await self.sender.send_model(
            TtsUnavailable(
                session_id=self.session_id,
                turn_id=turn_id,
                conversation_id=decision.conversation_id,
                dialog_id=decision.dialog_id,
                revision=decision.revision,
                purpose=purpose,
                text=decision.text,
            )
        )

    def _dialog_is_current(
        self,
        decision: (DialogClarificationDecision | DialogProposalDecision | DialogCompletedDecision),
    ) -> bool:
        if isinstance(decision, DialogClarificationDecision):
            expected_phase = DialogPhase.AWAITING_CLARIFICATION
        elif isinstance(decision, DialogProposalDecision):
            expected_phase = DialogPhase.AWAITING_CONFIRMATION
        else:
            expected_phase = DialogPhase.COMPLETED
        return bool(
            not self._closing
            and self.dialog is not None
            and self.dialog.phase is expected_phase
            and self.dialog.conversation_id == decision.conversation_id
            and self.dialog.current_dialog_id == decision.dialog_id
            and self.dialog.revision == decision.revision
        )

    async def _recommend(self, turn_id: str, transcript: str) -> None:
        based_on_version = self._turn_versions.pop(turn_id, self.based_on_cart_version)
        try:
            result = await self.container.recommendation_service.recommend(
                store_id=self.store_id,
                transcript=transcript,
            )
            common = {
                "session_id": self.session_id,
                "turn_id": _uuid(turn_id),
                "based_on_cart_version": based_on_version,
                "search_query": result.search_query,
                "quantity": result.quantity,
                "attributes": result.attributes,
                "degraded": result.degraded,
            }
            if result.candidates:
                await self.sender.send_model(
                    MenuCandidates(**common, candidates=list(result.candidates))
                )
                await self._send_tts(turn_id, result.candidates[0].name, result.quantity)
            else:
                await self.sender.send_model(NoMatch(**common))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("menu recommendation failed", extra={"turn_id": turn_id})
            await self._error(
                ErrorCode.INTERNAL_ERROR,
                "menu recommendation failed",
                retryable=True,
                turn_id=turn_id,
            )

    async def _send_tts(self, turn_id: str, menu_name: str, quantity: int) -> None:
        """Send optional TTS after candidates without affecting recommendation success."""

        tts_client = getattr(self.container, "tts_client", None)
        if tts_client is None or self._closing:
            return

        # Menu names are provider input and the public candidate contract allows
        # up to 500 characters. Keep spoken guidance deliberately short.
        spoken_name = menu_name.strip()[:200]
        if quantity > 1:
            text = f"{spoken_name} {quantity}잔을 추천드려요. 주문에 담을까요?"
        else:
            text = f"{spoken_name}을 추천드려요. 주문에 담을까요?"
        try:
            audio = await tts_client.synthesize(text)
            await self.sender.send_model(
                TtsAudio(
                    session_id=self.session_id,
                    turn_id=_uuid(turn_id),
                    media_type=audio.media_type,
                    audio_base64=base64.b64encode(audio.content).decode("ascii"),
                    text=text,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "TTS provider failed after menu recommendation",
                exc_info=True,
                extra={"session_id": str(self.session_id), "turn_id": turn_id},
            )

    async def _error(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool,
        turn_id: str | None = None,
    ) -> None:
        await self.sender.send_model(
            ErrorMessage(
                session_id=self.session_id,
                turn_id=_uuid(turn_id) if turn_id else None,
                code=code,
                message=message,
                retryable=retryable,
            )
        )


async def _reject_session_start(
    websocket: WebSocket,
    sender: WebSocketSender,
    *,
    code: ErrorCode,
    message: str,
    close_code: int,
    retryable: bool = False,
) -> None:
    with contextlib.suppress(Exception):
        await sender.send_model(ErrorMessage(code=code, message=message, retryable=retryable))
    with contextlib.suppress(Exception):
        await websocket.close(code=close_code)


@router.websocket("/ai/ws")
async def voice_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    sender = WebSocketSender(websocket)
    container = websocket.app.state.container
    timeout = container.settings.session_start_timeout_seconds
    try:
        first_message = await asyncio.wait_for(websocket.receive(), timeout=timeout)
        if first_message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(first_message.get("code", 1000))
        first = first_message.get("text")
        if not isinstance(first, str):
            raise ValueError("session.start must be a text frame")
        session_start = SessionStart.model_validate_json(first)
    except TimeoutError:
        await _reject_session_start(
            websocket,
            sender,
            code=ErrorCode.SESSION_START_TIMEOUT,
            message="session.start was not received in time",
            close_code=4408,
            retryable=True,
        )
        return
    except (ValidationError, ValueError, WebSocketDisconnect):
        await _reject_session_start(
            websocket,
            sender,
            code=ErrorCode.PROTOCOL_ERROR,
            message="the first message must be a valid session.start",
            close_code=4400,
        )
        return

    try:
        claims = container.token_verifier().verify(session_start.access_token)
    except (TokenValidationError, ValueError):
        await _reject_session_start(
            websocket,
            sender,
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="AI access token verification failed",
            close_code=4401,
        )
        return

    try:
        speech = container.create_speech_client()
        session = VoiceSession(
            websocket=websocket,
            container=container,
            session_id=uuid4(),
            order_session_id=claims.order_session_id,
            store_id=claims.store_id,
            session_start=session_start,
            speech=speech,
        )
        await session.run()
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("voice WebSocket session failed")
        await _reject_session_start(
            websocket,
            sender,
            code=ErrorCode.CLOVA_UNAVAILABLE,
            message="voice streaming service is unavailable",
            close_code=1011,
            retryable=True,
        )
