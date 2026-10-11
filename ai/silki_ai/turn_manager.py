"""Application-owned speech turn detection.

CLOVA's semantic EPD controls when recognition *results* are emitted.  It is
deliberately not used to decide when a user's turn is complete; that decision
is made here from the PCM stream and the latest transcript.
"""

from __future__ import annotations

import math
import struct
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class TurnState(StrEnum):
    IDLE = "idle"
    SPEAKING = "speaking"
    WAITING = "waiting"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


class TurnEventType(StrEnum):
    STARTED = "started"
    SPEECH_RESUMED = "speech_resumed"
    WAITING = "waiting"
    FINALIZE = "finalize"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class TurnEvent:
    type: TurnEventType
    turn_id: str
    state: TurnState
    reason: str | None = None


class InvalidAudioFrame(ValueError):
    """The application received PCM that does not match its audio contract."""


CompletionDetector = Callable[[str], bool]
TurnIdFactory = Callable[[], str]


def default_completion_detector(text: str) -> bool:
    """Conservatively identify transcripts that sound syntactically complete.

    It is intentionally deterministic and small.  Product-specific language
    models can be injected through ``completion_detector`` without changing
    turn timing or allowing semantic EPD to finalize a turn.
    """

    normalized = " ".join(text.strip().split())
    if not normalized:
        return False
    if normalized.endswith((".", "!", "?", "。", "！", "？")):
        return True

    last = normalized.rsplit(" ", 1)[-1]
    incomplete_words = {
        "그리고",
        "그래서",
        "그런데",
        "하지만",
        "또",
        "또는",
        "아니면",
        "하고",
        "랑",
        "이랑",
        "좀",
    }
    incomplete_suffixes = ("고", "거나", "는데", "지만", "면서", "면", "서")
    return last not in incomplete_words and not last.endswith(incomplete_suffixes)


class TurnManager:
    """Frame-based VAD and single-active-turn state machine.

    The default contract is headerless little-endian 16 kHz, mono, signed
    16-bit PCM in 20 ms frames.  Silence timing is derived from audio frames,
    making the class deterministic and independent of event-loop scheduling.
    """

    def __init__(
        self,
        *,
        sample_rate_hz: int = 16_000,
        channels: int = 1,
        sample_width_bytes: int = 2,
        frame_duration_ms: int = 20,
        silence_seconds: float = 1.5,
        incomplete_silence_seconds: float = 2.5,
        max_turn_seconds: float = 15.0,
        transcript_stable_seconds: float = 3.0,
        min_rms_dbfs: float = -45.0,
        completion_detector: CompletionDetector = default_completion_detector,
        turn_id_factory: TurnIdFactory | None = None,
    ) -> None:
        if sample_rate_hz <= 0 or channels != 1 or sample_width_bytes != 2:
            raise ValueError("TurnManager requires positive-rate mono 16-bit PCM")
        if frame_duration_ms <= 0:
            raise ValueError("frame_duration_ms must be positive")
        samples_per_frame = sample_rate_hz * frame_duration_ms
        if samples_per_frame % 1000:
            raise ValueError("frame_duration_ms must produce a whole number of samples")
        if not 0 < silence_seconds <= incomplete_silence_seconds:
            raise ValueError("silence thresholds must satisfy 0 < normal <= incomplete")
        if max_turn_seconds < incomplete_silence_seconds:
            raise ValueError("max turn duration must be at least the incomplete silence timeout")
        if transcript_stable_seconds < 0:
            raise ValueError("transcript stability timeout must be disabled with 0 or positive")
        if not -80.0 <= min_rms_dbfs <= -10.0:
            raise ValueError("min_rms_dbfs must be between -80 and -10")

        self.sample_rate_hz = sample_rate_hz
        self.channels = channels
        self.sample_width_bytes = sample_width_bytes
        self.frame_duration_ms = frame_duration_ms
        self.samples_per_frame = samples_per_frame // 1000
        self.frame_bytes = self.samples_per_frame * channels * sample_width_bytes
        self.silence_frame_limit = math.ceil(silence_seconds * 1000 / frame_duration_ms)
        self.incomplete_frame_limit = math.ceil(
            incomplete_silence_seconds * 1000 / frame_duration_ms
        )
        self.max_turn_frame_limit = math.ceil(max_turn_seconds * 1000 / frame_duration_ms)
        self.transcript_stable_frame_limit = (
            math.ceil(transcript_stable_seconds * 1000 / frame_duration_ms)
            if transcript_stable_seconds > 0
            else None
        )
        self.min_rms_dbfs = min_rms_dbfs
        self.completion_detector = completion_detector
        self._turn_id_factory = turn_id_factory or (lambda: str(uuid.uuid4()))

        self.state = TurnState.IDLE
        self.current_turn_id: str | None = None
        self.transcript = ""
        self._completion_override: bool | None = None
        self._silence_frames = 0
        self._active_frames = 0
        self._transcript_stable_frames = 0
        self._chunk_buffer = bytearray()

    @property
    def active_turn_id(self) -> str | None:
        if self.state in (TurnState.SPEAKING, TurnState.WAITING, TurnState.FINALIZING):
            return self.current_turn_id
        return None

    @property
    def silence_ms(self) -> int:
        return self._silence_frames * self.frame_duration_ms

    @property
    def active_ms(self) -> int:
        return self._active_frames * self.frame_duration_ms

    @property
    def transcript_stable_ms(self) -> int:
        """Audio time elapsed since the latest distinct non-empty STT text."""

        return self._transcript_stable_frames * self.frame_duration_ms

    def rms_dbfs(self, pcm_frame: bytes) -> float:
        """Return PCM16 RMS energy in dBFS, using ``-inf`` for digital silence."""

        if len(pcm_frame) != self.frame_bytes:
            raise InvalidAudioFrame(
                f"expected {self.frame_bytes} bytes ({self.frame_duration_ms} ms), "
                f"received {len(pcm_frame)}"
            )
        samples = struct.unpack(f"<{self.samples_per_frame}h", pcm_frame)
        mean_square = sum(sample * sample for sample in samples) / len(samples)
        if mean_square == 0:
            return -math.inf
        rms = math.sqrt(mean_square)
        return 20.0 * math.log10(rms / 32768.0)

    def update_transcript(self, text: str, *, is_complete: bool | None = None) -> None:
        """Store the latest assembled STT text without changing turn state.

        ``is_complete`` is an optional application hint.  In particular, a
        semantic EPD response should call this method but must not call
        :meth:`force_finalize` merely because CLOVA emitted a result.
        """

        normalized = text.strip()
        if normalized != self.transcript:
            # CLOVA can repeat the same partial. Only a genuinely extended or
            # corrected transcript proves that the user is still speaking.
            self._transcript_stable_frames = 0
        self.transcript = normalized
        self._completion_override = is_complete

    def on_stt_result(
        self,
        text: str,
        *,
        semantic_epd: bool = False,
        is_complete: bool | None = None,
    ) -> None:
        # ``semantic_epd`` is accepted to make the separation explicit.  It is
        # metadata only and intentionally cannot transition the state machine.
        del semantic_epd
        self.update_transcript(text, is_complete=is_complete)

    def process_frame(self, pcm_frame: bytes, *, voiced: bool | None = None) -> list[TurnEvent]:
        """Process exactly one PCM frame and return state-transition events."""

        if len(pcm_frame) != self.frame_bytes:
            raise InvalidAudioFrame(
                f"expected {self.frame_bytes} bytes ({self.frame_duration_ms} ms), "
                f"received {len(pcm_frame)}"
            )
        # A positive WebRTC VAD decision is necessary but not sufficient. In
        # browsers, AGC and steady room noise can keep WebRTC VAD active for
        # minutes. Requiring an independently configurable dBFS energy floor
        # prevents that noise from continuously resetting the silence timer.
        energy_voiced = self.rms_dbfs(pcm_frame) >= self.min_rms_dbfs
        speech = energy_voiced if voiced is None else voiced and energy_voiced
        events: list[TurnEvent] = []

        if self.state is TurnState.FINALIZING:
            # The caller must flush STT and complete the active turn before a
            # new turn can start. Audio can continue arriving meanwhile.
            return events

        if speech:
            if self.state in (TurnState.IDLE, TurnState.COMPLETED):
                self._start_turn()
                events.append(self._event(TurnEventType.STARTED, reason="voice_activity"))
            elif self.state is TurnState.WAITING:
                self.state = TurnState.SPEAKING
                self._silence_frames = 0
                events.append(self._event(TurnEventType.SPEECH_RESUMED, reason="voice_activity"))
            self._active_frames += 1
            if self._active_frames >= self.max_turn_frame_limit:
                events.append(self._request_finalize("max_duration"))
            elif self._advance_transcript_stability():
                events.append(self._request_finalize("transcript_stable_timeout"))
            return events

        if self.state is TurnState.SPEAKING:
            self.state = TurnState.WAITING
            self._silence_frames = 1
            self._active_frames += 1
            events.append(self._event(TurnEventType.WAITING, reason="silence"))
        elif self.state is TurnState.WAITING:
            self._silence_frames += 1
            self._active_frames += 1
        else:
            return events

        complete = (
            self._completion_override
            if self._completion_override is not None
            else self.completion_detector(self.transcript)
        )
        if complete and self._silence_frames >= self.silence_frame_limit:
            events.append(self._request_finalize("silence"))
        elif self._silence_frames >= self.incomplete_frame_limit:
            events.append(self._request_finalize("incomplete_timeout"))
        elif self._active_frames >= self.max_turn_frame_limit:
            events.append(self._request_finalize("max_duration"))
        elif self._advance_transcript_stability():
            events.append(self._request_finalize("transcript_stable_timeout"))
        return events

    def feed_audio(self, pcm_chunk: bytes) -> list[TurnEvent]:
        """Process an arbitrary chunk, retaining a trailing partial frame."""

        self._chunk_buffer.extend(pcm_chunk)
        events: list[TurnEvent] = []
        while len(self._chunk_buffer) >= self.frame_bytes:
            frame = bytes(self._chunk_buffer[: self.frame_bytes])
            del self._chunk_buffer[: self.frame_bytes]
            events.extend(self.process_frame(frame))
        return events

    def force_finalize(self, reason: str = "client_requested") -> TurnEvent | None:
        """Move a started turn to finalizing, once."""

        if self.state in (TurnState.SPEAKING, TurnState.WAITING):
            return self._request_finalize(reason)
        return None

    def complete_turn(self, turn_id: str | None = None) -> TurnEvent:
        """Complete the flushed turn so the next voiced frame gets a new ID."""

        if self.state is not TurnState.FINALIZING or self.current_turn_id is None:
            raise RuntimeError("no finalizing turn to complete")
        if turn_id is not None and turn_id != self.current_turn_id:
            raise ValueError("turn_id does not match the active turn")
        completed_id = self.current_turn_id
        self.state = TurnState.COMPLETED
        self.current_turn_id = None
        self.transcript = ""
        self._completion_override = None
        self._silence_frames = 0
        self._active_frames = 0
        self._transcript_stable_frames = 0
        return TurnEvent(TurnEventType.COMPLETED, completed_id, self.state, "stt_flushed")

    def reset(self) -> None:
        self.state = TurnState.IDLE
        self.current_turn_id = None
        self.transcript = ""
        self._completion_override = None
        self._silence_frames = 0
        self._active_frames = 0
        self._transcript_stable_frames = 0
        self._chunk_buffer.clear()

    def _start_turn(self) -> None:
        self.current_turn_id = self._turn_id_factory()
        self.state = TurnState.SPEAKING
        self.transcript = ""
        self._completion_override = None
        self._silence_frames = 0
        self._active_frames = 0
        self._transcript_stable_frames = 0

    def _request_finalize(self, reason: str) -> TurnEvent:
        self.state = TurnState.FINALIZING
        return self._event(TurnEventType.FINALIZE, reason=reason)

    def _event(self, event_type: TurnEventType, *, reason: str | None = None) -> TurnEvent:
        if self.current_turn_id is None:
            raise RuntimeError("turn event requires an active turn")
        return TurnEvent(event_type, self.current_turn_id, self.state, reason)

    def _advance_transcript_stability(self) -> bool:
        """Return true once useful STT text has stopped changing long enough.

        This is a trailing safety valve for rooms where steady noise keeps
        WebRTC VAD positive. It is deliberately based on audio-frame time, not
        wall-clock scheduling, and is disabled when the configured value is 0.
        """

        if self.transcript_stable_frame_limit is None or not self.transcript:
            self._transcript_stable_frames = 0
            return False
        self._transcript_stable_frames += 1
        return self._transcript_stable_frames >= self.transcript_stable_frame_limit

    def _is_voiced(self, pcm_frame: bytes) -> bool:
        return self.rms_dbfs(pcm_frame) >= self.min_rms_dbfs
