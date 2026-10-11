from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr, ValidationError

from silki_ai.clova import build_keyword_boosting_config
from silki_ai.config import Settings
from silki_ai.container import ApplicationContainer
from silki_ai.tts import EdgeTtsClient, FishSpeechTtsClient


def test_settings_coerces_vad_aggressiveness_from_environment_string() -> None:
    settings = Settings(_env_file=None, vad_aggressiveness="2")

    assert settings.vad_aggressiveness == 2


def test_settings_validate_vad_dbfs_floor_and_max_turn_duration() -> None:
    settings = Settings(
        _env_file=None,
        vad_min_rms_dbfs=-42.5,
        turn_max_seconds=12,
        turn_transcript_stable_seconds=3.5,
    )

    assert settings.vad_min_rms_dbfs == -42.5
    assert settings.turn_max_seconds == 12
    assert settings.turn_transcript_stable_seconds == 3.5

    with pytest.raises(ValidationError):
        Settings(_env_file=None, vad_min_rms_dbfs=-5)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, turn_transcript_stable_seconds=-0.1)
    with pytest.raises(ValidationError, match="turn_max_seconds"):
        Settings(
            _env_file=None,
            turn_incomplete_silence_seconds=2.5,
            turn_max_seconds=2,
        )


def test_settings_use_spring_integration_security_and_menu_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.jwt_algorithms == ("RS256",)
    assert settings.jwt_audience == "ai-ws"
    assert settings.jwt_issuer == "silki-be"
    assert settings.jwt_max_ttl_seconds == 180
    assert settings.menu_source_table == "public.ai_menu_source"


def test_tts_defaults_to_disabled_and_can_select_edge_for_local_use() -> None:
    edge_settings = Settings(_env_file=None, tts_provider="edge")
    edge_container = ApplicationContainer(edge_settings)

    disabled_settings = Settings(_env_file=None)
    disabled_container = ApplicationContainer(disabled_settings)

    assert edge_settings.effective_tts_provider == "edge"
    assert isinstance(edge_container.tts_client, EdgeTtsClient)
    assert disabled_settings.effective_tts_provider == "disabled"
    assert disabled_container.tts_client is None


def test_container_selects_fish_with_new_provider_setting() -> None:
    settings = Settings(
        _env_file=None,
        tts_provider="fish",
        fish_tts_base_url="http://10.0.2.15:8080",
        fish_tts_api_key=SecretStr("secret"),
    )
    container = ApplicationContainer(settings)

    assert settings.effective_tts_provider == "fish"
    assert isinstance(container.tts_client, FishSpeechTtsClient)


@pytest.mark.parametrize("algorithms", [["ES256"], ["RS256", "ES256"], ["HS256"]])
def test_settings_reject_non_rs256_algorithm_sets(algorithms: list[str]) -> None:
    with pytest.raises(ValidationError, match="RS256 only"):
        Settings(_env_file=None, jwt_algorithms=algorithms)


def test_settings_rejects_jwt_ttl_above_integration_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_max_ttl_seconds=181)


@pytest.mark.asyncio
async def test_readiness_requires_a_parseable_rsa_verification_key() -> None:
    invalid_container = ApplicationContainer(
        Settings(_env_file=None, jwt_public_key="configured-but-invalid")
    )
    invalid_checks = await invalid_container.readiness()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    valid_container = ApplicationContainer(Settings(_env_file=None, jwt_public_key=public_key))
    valid_checks = await valid_container.readiness()

    assert invalid_checks["jwtVerificationKey"] is False
    assert valid_checks["jwtVerificationKey"] is True

    await invalid_container.close()
    await valid_container.close()


@pytest.mark.parametrize("frame_duration_ms", [15, 40, 100])
def test_settings_rejects_vad_unsupported_frame_durations(frame_duration_ms: int) -> None:
    with pytest.raises(ValueError, match="WebRTC VAD"):
        Settings(_env_file=None, audio_frame_duration_ms=frame_duration_ms)


def test_container_respects_semantic_epd_disable_flag() -> None:
    settings = Settings(
        _env_file=None,
        clova_secret_key=SecretStr("test-secret"),
        clova_semantic_epd=False,
    )
    container = ApplicationContainer(settings)

    speech = container.create_speech_client()

    assert speech.semantic_epd == {}


def test_container_configures_semantic_epd_as_transcription_hint_only() -> None:
    settings = Settings(
        _env_file=None,
        clova_secret_key=SecretStr("test-secret"),
        clova_semantic_epd=True,
        turn_silence_seconds=1.5,
    )
    container = ApplicationContainer(settings)

    speech = container.create_speech_client()

    assert speech.semantic_epd["gapThreshold"] == 1500


def test_container_loads_code_side_keywords_at_weight_five(tmp_path) -> None:
    keyword_file = tmp_path / "keywords.txt"
    keyword_file.write_text("아이스 아메리카노\n아아\n아아\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        clova_secret_key=SecretStr("test-secret"),
        clova_keyword_file=keyword_file,
        clova_keyword_weight=5,
    )
    container = ApplicationContainer(settings)

    speech = container.create_speech_client()

    assert speech.boosting_keywords == ("아이스 아메리카노", "아아")
    assert build_keyword_boosting_config(
        speech.boosting_groups,
        weight=speech.keyword_boosting_weight,
    ) == {
        "useDomainBoostings": False,
        "keywordBoosting": {
            "boostings": [
                {"words": "아이스 아메리카노,아아", "weight": 5.0},
            ]
        },
    }
    assert speech.keyword_boosting_weight == 5.0


def test_container_can_disable_code_side_keyword_boosting() -> None:
    settings = Settings(
        _env_file=None,
        clova_secret_key=SecretStr("test-secret"),
        clova_keyword_boosting_enabled=False,
    )
    container = ApplicationContainer(settings)

    speech = container.create_speech_client()

    assert speech.boosting_keywords == ()
