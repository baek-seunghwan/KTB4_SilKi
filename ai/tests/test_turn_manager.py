from __future__ import annotations

import struct

import pytest

from silki_ai.turn_manager import (
    InvalidAudioFrame,
    TurnEventType,
    TurnManager,
    TurnState,
)


def pcm_frame(amplitude: int, samples: int = 320) -> bytes:
    return struct.pack(f"<{samples}h", *([amplitude] * samples))


SPEECH = pcm_frame(2_000)
SILENCE = pcm_frame(0)
LOW_NOISE = pcm_frame(100)


def manager(**kwargs: object) -> TurnManager:
    ids = iter(("turn-1", "turn-2", "turn-3"))
    return TurnManager(turn_id_factory=lambda: next(ids), **kwargs)


def test_complete_transcript_finalizes_after_default_silence() -> None:
    turns = manager()

    started = turns.process_frame(SPEECH)
    turns.update_transcript("아메리카노 주세요")
    events = []
    for _ in range(75):
        events.extend(turns.process_frame(SILENCE))

    assert started[0].type is TurnEventType.STARTED
    assert started[0].turn_id == "turn-1"
    assert events[-1].type is TurnEventType.FINALIZE
    assert events[-1].reason == "silence"
    assert events[-1].turn_id == "turn-1"
    assert turns.state is TurnState.FINALIZING
    assert turns.silence_ms == 1_500


def test_incomplete_transcript_waits_until_extended_timeout() -> None:
    turns = manager()
    turns.process_frame(SPEECH)
    turns.update_transcript("아메리카노하고", is_complete=False)

    first_window = []
    for _ in range(75):
        first_window.extend(turns.process_frame(SILENCE))
    assert turns.state is TurnState.WAITING
    assert not any(event.type is TurnEventType.FINALIZE for event in first_window)

    extension = []
    for _ in range(50):
        extension.extend(turns.process_frame(SILENCE))
    assert extension[-1].type is TurnEventType.FINALIZE
    assert extension[-1].reason == "incomplete_timeout"
    assert turns.silence_ms == 2_500


def test_semantic_epd_updates_text_but_never_finalizes_turn() -> None:
    turns = manager()
    turns.process_frame(SPEECH)

    turns.on_stt_result("차가운 음료", semantic_epd=True, is_complete=True)

    assert turns.state is TurnState.SPEAKING
    assert turns.transcript == "차가운 음료"
    assert turns.force_finalize() is not None  # only application action changes state


def test_speech_resume_cancels_silence_and_completion_starts_new_id() -> None:
    turns = manager()
    turns.process_frame(SPEECH)
    turns.update_transcript("따뜻한 차", is_complete=True)
    for _ in range(50):
        turns.process_frame(SILENCE)

    resumed = turns.process_frame(SPEECH)
    assert resumed[0].type is TurnEventType.SPEECH_RESUMED
    assert turns.state is TurnState.SPEAKING
    assert turns.silence_ms == 0

    finalize = turns.force_finalize("session_end")
    assert finalize is not None
    completed = turns.complete_turn("turn-1")
    assert completed.type is TurnEventType.COMPLETED
    assert turns.active_turn_id is None

    next_started = turns.process_frame(SPEECH)
    assert next_started[0].turn_id == "turn-2"


def test_feed_audio_buffers_partial_frames_and_validates_direct_frames() -> None:
    turns = manager()

    assert turns.feed_audio(SPEECH[:100]) == []
    events = turns.feed_audio(SPEECH[100:])
    assert events[0].type is TurnEventType.STARTED

    with pytest.raises(InvalidAudioFrame):
        turns.process_frame(b"short")


def test_webrtcvad_positive_still_requires_configured_dbfs_energy_floor() -> None:
    turns = manager(min_rms_dbfs=-45.0)

    assert turns.rms_dbfs(LOW_NOISE) == pytest.approx(-50.31, abs=0.02)
    assert turns.process_frame(LOW_NOISE, voiced=True) == []
    assert turns.state is TurnState.IDLE

    started = turns.process_frame(SPEECH, voiced=True)
    assert turns.rms_dbfs(SPEECH) == pytest.approx(-24.29, abs=0.02)
    assert started[0].type is TurnEventType.STARTED


def test_max_turn_duration_finalizes_continuous_voiced_audio() -> None:
    turns = manager(
        silence_seconds=0.02,
        incomplete_silence_seconds=0.04,
        max_turn_seconds=0.06,
    )

    events = []
    for _ in range(3):
        events.extend(turns.process_frame(SPEECH, voiced=True))

    assert events[-1].type is TurnEventType.FINALIZE
    assert events[-1].reason == "max_duration"
    assert turns.state is TurnState.FINALIZING
    assert turns.active_ms == 60


def test_stable_transcript_finalizes_even_when_noise_keeps_vad_voiced() -> None:
    turns = manager(
        silence_seconds=0.02,
        incomplete_silence_seconds=0.04,
        max_turn_seconds=1.0,
        transcript_stable_seconds=0.06,
    )
    turns.process_frame(SPEECH, voiced=True)
    turns.update_transcript("아이스 아메리카노 한 잔")

    events = []
    for _ in range(3):
        # This deliberately remains acoustically voiced, as happens when
        # steady room noise fools WebRTC VAD.
        events.extend(turns.process_frame(SPEECH, voiced=True))

    assert events[-1].type is TurnEventType.FINALIZE
    assert events[-1].reason == "transcript_stable_timeout"
    assert turns.transcript_stable_ms == 60
    assert turns.active_ms < 1_000


def test_only_distinct_transcript_updates_reset_stability_timeout() -> None:
    turns = manager(
        silence_seconds=0.02,
        incomplete_silence_seconds=0.04,
        max_turn_seconds=1.0,
        transcript_stable_seconds=0.06,
    )
    turns.process_frame(SPEECH, voiced=True)
    turns.update_transcript("아이스 아메리카노")
    turns.process_frame(SPEECH, voiced=True)
    turns.process_frame(SPEECH, voiced=True)

    turns.update_transcript("아이스 아메리카노")
    assert turns.transcript_stable_ms == 40

    turns.update_transcript("아이스 아메리카노 한 잔")
    assert turns.transcript_stable_ms == 0
    assert turns.process_frame(SPEECH, voiced=True) == []
    assert turns.process_frame(SPEECH, voiced=True) == []
    events = turns.process_frame(SPEECH, voiced=True)

    assert events[-1].reason == "transcript_stable_timeout"


def test_transcript_stability_timeout_can_be_disabled() -> None:
    turns = manager(
        silence_seconds=0.02,
        incomplete_silence_seconds=0.04,
        max_turn_seconds=0.08,
        transcript_stable_seconds=0,
    )
    turns.process_frame(SPEECH, voiced=True)
    turns.update_transcript("길게 말하는 중")

    assert turns.process_frame(SPEECH, voiced=True) == []
    assert turns.process_frame(SPEECH, voiced=True) == []
    events = turns.process_frame(SPEECH, voiced=True)

    assert events[-1].reason == "max_duration"
    assert turns.transcript_stable_ms == 0
