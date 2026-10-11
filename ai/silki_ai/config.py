"""Application configuration loaded from environment variables.

The defaults are suitable for local development. Production secrets are intentionally
optional here so importing the application (and running unit tests) never requires
access to an external secret store. Components that use a secret validate its
presence when they are constructed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_ALGORITHM = "RS256"


class Settings(BaseSettings):
    """Runtime settings for the Silki AI service."""

    model_config = SettingsConfigDict(
        env_prefix="SILKI_AI_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "silki-ai"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    session_start_timeout_seconds: float = Field(default=3.0, gt=0)
    websocket_idle_timeout_seconds: float = Field(default=120.0, gt=0)

    jwt_public_key: str = ""
    jwt_algorithms: tuple[str, ...] = (JWT_ALGORITHM,)
    jwt_audience: str = Field(default="ai-ws", min_length=1, max_length=256)
    jwt_issuer: str = Field(default="silki-be", min_length=1, max_length=256)
    jwt_leeway_seconds: int = Field(default=5, ge=0, le=60)
    jwt_max_ttl_seconds: int = Field(default=180, gt=0, le=180)

    audio_sample_rate_hz: Literal[16000] = 16000
    audio_channels: Literal[1] = 1
    audio_sample_width_bytes: Literal[2] = 2
    audio_byte_order: Literal["little"] = "little"
    audio_frame_duration_ms: int = Field(default=20, ge=10, le=100)
    vad_aggressiveness: Literal[0, 1, 2, 3] = 2
    # WebRTC VAD alone can classify steady browser/room noise as speech.  Keep
    # it as the primary speech detector, but require a small PCM energy floor
    # expressed in dBFS (0 dBFS is full-scale PCM16; normal speech is negative).
    vad_min_rms_dbfs: float = Field(default=-45.0, ge=-80.0, le=-10.0)
    # The VAD/energy gate only turns positive once the utterance is already
    # loud enough, so the onset -- in Korean typically an unvoiced stop or
    # fricative well below the dBFS floor -- would never reach the recognizer.
    # Keep this much audio from just before the gate opened and send it first.
    audio_preroll_ms: int = Field(default=300, ge=0, le=2000)

    turn_silence_seconds: float = Field(default=1.5, gt=0)
    turn_incomplete_silence_seconds: float = Field(default=2.5, gt=0)
    turn_max_seconds: float = Field(default=15.0, gt=0, le=60.0)
    # If CLOVA has useful text but steady noise keeps VAD positive, finalize
    # after the text has stopped changing for this much streamed-audio time.
    # Set to 0 to disable; the absolute maximum turn duration always remains.
    turn_transcript_stable_seconds: float = Field(default=3.0, ge=0, le=60.0)
    clova_flush_timeout_seconds: float = Field(default=2.0, gt=0)

    clova_grpc_target: str = "clovaspeech-gw.ncloud.com:50051"
    clova_secret_key: SecretStr | None = None
    clova_language: Literal["ko", "en", "ja"] = "ko"
    clova_semantic_epd: bool = True
    clova_keyword_boosting_enabled: bool = True
    clova_keyword_weight: float = Field(default=5.0, ge=0, le=5)
    clova_keyword_file: Path | None = None

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = Field(default=3.0, gt=0)

    # Fail closed when deployment configuration is absent. The local
    # integration configurator explicitly selects ``edge`` for demos.
    tts_provider: Literal["edge", "fish", "disabled"] = "disabled"
    tts_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    tts_max_audio_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1024,
        le=8 * 1024 * 1024,
    )
    edge_tts_voice: str = Field(default="ko-KR-SunHiNeural", min_length=1, max_length=128)
    edge_tts_rate: str = Field(default="-5%", pattern=r"^[+-]\d{1,3}%$")
    edge_tts_volume: str = Field(default="+0%", pattern=r"^[+-]\d{1,3}%$")
    edge_tts_pitch: str = Field(default="+0Hz", pattern=r"^[+-]\d{1,4}Hz$")

    # Deprecated compatibility switch. If TTS_PROVIDER was not supplied,
    # existing deployments with FISH_TTS_ENABLED=true continue to select Fish.
    fish_tts_enabled: bool = False
    fish_tts_base_url: str = ""
    fish_tts_api_key: SecretStr | None = None
    fish_tts_reference_id: str | None = Field(default=None, max_length=255)
    fish_tts_format: Literal["wav", "mp3", "opus"] = "mp3"
    fish_tts_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    fish_tts_max_audio_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1024,
        le=8 * 1024 * 1024,
    )

    database_url: str = "postgresql://silki:silki@localhost:5432/silki"
    menu_source_table: str = "public.ai_menu_source"
    embedding_table: str = "ai.menu_embeddings"
    reindex_state_table: str = "ai.reindex_state"
    embedding_dimension: int = Field(default=768, gt=0)
    embedding_preload: bool = False
    auto_create_schema: bool = False
    embedding_model_name: str = "jhgan/ko-sroberta-multitask"
    search_top_k: int = Field(default=3, ge=1, le=20)
    search_score_threshold: float = Field(default=0.45, ge=0, le=1)

    internal_api_key: SecretStr | None = None

    @field_validator("jwt_public_key", mode="before")
    @classmethod
    def restore_pem_newlines(cls, value: object) -> object:
        """Allow a PEM key to be supplied as a single-line environment value."""

        if isinstance(value, str):
            return value.replace("\\n", "\n").strip()
        return value

    @field_validator("jwt_audience", "jwt_issuer", mode="before")
    @classmethod
    def strip_required_jwt_identifiers(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("fish_tts_base_url", mode="before")
    @classmethod
    def strip_fish_tts_base_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().rstrip("/")
        return value

    @field_validator("edge_tts_voice", mode="before")
    @classmethod
    def strip_edge_tts_voice(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator(
        "clova_secret_key",
        "clova_keyword_file",
        "gemini_api_key",
        "fish_tts_api_key",
        "fish_tts_reference_id",
        "internal_api_key",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("vad_aggressiveness", mode="before")
    @classmethod
    def coerce_vad_aggressiveness(cls, value: object) -> object:
        """Convert integer environment variables before validating the allowed range."""

        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        return value

    @field_validator("audio_frame_duration_ms")
    @classmethod
    def require_webrtcvad_compatible_frame_duration(cls, value: int) -> int:
        """Reject frame lengths that make WebRTC VAD fail for every frame."""

        if value not in {10, 20, 30}:
            raise ValueError("audio_frame_duration_ms must be one of 10, 20, or 30 for WebRTC VAD")
        return value

    @field_validator("jwt_algorithms")
    @classmethod
    def require_asymmetric_algorithms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(algorithm.upper() for algorithm in value))
        if normalized != (JWT_ALGORITHM,):
            raise ValueError("JWT algorithms must contain RS256 only")
        return normalized

    @model_validator(mode="after")
    def validate_timeouts(self) -> Settings:
        if self.turn_incomplete_silence_seconds < self.turn_silence_seconds:
            raise ValueError(
                "turn_incomplete_silence_seconds must be greater than or equal to "
                "turn_silence_seconds"
            )
        if self.turn_max_seconds < self.turn_incomplete_silence_seconds:
            raise ValueError(
                "turn_max_seconds must be greater than or equal to "
                "turn_incomplete_silence_seconds"
            )
        if self.websocket_idle_timeout_seconds <= self.session_start_timeout_seconds:
            raise ValueError(
                "websocket_idle_timeout_seconds must exceed session_start_timeout_seconds"
            )
        if self.fish_tts_base_url:
            parsed = urlsplit(self.fish_tts_base_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "fish_tts_base_url must be an HTTP(S) origin without credentials, "
                    "query, or fragment"
                )
            if parsed.path.rstrip("/"):
                raise ValueError("fish_tts_base_url must not contain a path")
        if self.effective_tts_provider == "fish":
            if not self.fish_tts_base_url:
                raise ValueError("fish_tts_base_url is required when Fish Audio is selected")
            if self.fish_tts_api_key is None:
                raise ValueError("fish_tts_api_key is required when Fish Audio is selected")
        return self

    @property
    def effective_tts_provider(self) -> Literal["edge", "fish", "disabled"]:
        """Resolve the new selector while preserving the legacy Fish flag."""

        if self.fish_tts_enabled and "tts_provider" not in self.model_fields_set:
            return "fish"
        return self.tts_provider

    @property
    def preroll_frame_count(self) -> int:
        """Frames of pre-gate audio to replay, truncated to whole frames."""

        return self.audio_preroll_ms // self.audio_frame_duration_ms

    @property
    def pcm_frame_bytes(self) -> int:
        """Expected bytes in one PCM frame at the configured frame duration."""

        samples = self.audio_sample_rate_hz * self.audio_frame_duration_ms // 1000
        return samples * self.audio_channels * self.audio_sample_width_bytes


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable-by-convention settings instance."""

    return Settings()
