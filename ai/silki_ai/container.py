"""Application composition root for provider, database, and domain services."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from psycopg_pool import AsyncConnectionPool
from webrtcvad import Vad

from silki_ai.clova import ClovaStreamingClient, load_clova_keyword_groups
from silki_ai.config import Settings
from silki_ai.embeddings import SentenceTransformerEmbedder
from silki_ai.nlp import GeminiQueryNormalizer
from silki_ai.pgvector_store import PgVectorMenuStore
from silki_ai.recommendation import MenuRecommendationService
from silki_ai.reindex import MenuReindexService
from silki_ai.security import AccessTokenVerifier
from silki_ai.tts import EdgeTtsClient, FishSpeechTtsClient


class ApplicationContainer:
    """Own long-lived resources and create connection-scoped speech clients."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            open=False,
        )
        self.menu_store = PgVectorMenuStore(
            self.pool,
            menu_table=settings.menu_source_table,
            embedding_table=settings.embedding_table,
            revision_table=settings.reindex_state_table,
            embedding_dimension=settings.embedding_dimension,
        )
        self.embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
        prompt_candidates = (
            Path(__file__).resolve().parent / "prompts" / "query_refinement.ko.md",
            Path(__file__).resolve().parents[1] / "prompts" / "query_refinement.ko.md",
        )
        prompt_path = next((path for path in prompt_candidates if path.exists()), None)
        self.query_normalizer = GeminiQueryNormalizer(
            api_key=(
                settings.gemini_api_key.get_secret_value()
                if settings.gemini_api_key is not None
                else None
            ),
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            prompt_path=prompt_path,
        )
        self.recommendation_service = MenuRecommendationService(
            self.query_normalizer,
            self.embedder,
            self.menu_store,
            top_k=min(settings.search_top_k, 3),
            score_threshold=settings.search_score_threshold,
        )
        self.reindex_service = MenuReindexService(self.menu_store, self.embedder)
        tts_provider = settings.effective_tts_provider
        if tts_provider == "edge":
            self.tts_client = EdgeTtsClient(
                voice=settings.edge_tts_voice,
                rate=settings.edge_tts_rate,
                volume=settings.edge_tts_volume,
                pitch=settings.edge_tts_pitch,
                timeout_seconds=settings.tts_timeout_seconds,
                max_audio_bytes=settings.tts_max_audio_bytes,
            )
        elif tts_provider == "fish":
            if settings.fish_tts_api_key is None:  # guarded by Settings validation
                raise ValueError("Fish Audio API key is not configured")
            self.tts_client = FishSpeechTtsClient(
                base_url=settings.fish_tts_base_url,
                api_key=settings.fish_tts_api_key.get_secret_value(),
                audio_format=settings.fish_tts_format,
                reference_id=settings.fish_tts_reference_id,
                timeout_seconds=settings.fish_tts_timeout_seconds,
                max_audio_bytes=settings.fish_tts_max_audio_bytes,
            )
        else:
            self.tts_client = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.pool.open()
        try:
            if self.settings.auto_create_schema:
                await self.menu_store.initialize(create_extension=True)
            if self.settings.embedding_preload:
                await self.embedder.warmup()
        except Exception:
            await self.pool.close()
            raise
        self._started = True

    async def close(self) -> None:
        try:
            if self.tts_client is not None:
                await self.tts_client.aclose()
        finally:
            try:
                await self.query_normalizer.aclose()
            finally:
                if not self.pool.closed:
                    await self.pool.close()
                self._started = False

    async def readiness(self) -> dict[str, bool]:
        database_ready = False
        schema_ready = False
        menu_source_ready = False
        menu_source_exists = False
        if self._started and not self.pool.closed:
            try:
                await self.pool.check()
                database_ready = True
                async with self.pool.connection() as connection:
                    async with connection.cursor() as cursor:
                        await cursor.execute(
                            "SELECT "
                            "to_regclass(%s) IS NOT NULL, "
                            "to_regclass(%s) IS NOT NULL, "
                            "to_regclass(%s) IS NOT NULL",
                            (
                                self.settings.menu_source_table,
                                self.settings.embedding_table,
                                self.settings.reindex_state_table,
                            ),
                        )
                        row = await cursor.fetchone()
                        if row is not None:
                            menu_source_exists = bool(row[0])
                            schema_ready = all(bool(value) for value in row[1:])
            except Exception:
                database_ready = False
                schema_ready = False
                menu_source_exists = False
        if database_ready and menu_source_exists:
            try:
                await self.menu_store.check_source_contract()
                menu_source_ready = True
            except Exception:
                menu_source_ready = False
        try:
            self.token_verifier()
            jwt_verification_ready = True
        except (TypeError, ValueError):
            jwt_verification_ready = False
        return {
            "database": database_ready,
            "databaseSchema": schema_ready,
            "menuSourceRelation": menu_source_ready,
            "jwtVerificationKey": jwt_verification_ready,
            "clovaCredentials": bool(self.settings.clova_secret_key),
            "clovaProtocol": (
                importlib.util.find_spec("silki_ai.generated.nest_pb2") is not None
                and importlib.util.find_spec("silki_ai.generated.nest_pb2_grpc") is not None
            ),
            "internalApiCredentials": bool(self.settings.internal_api_key),
            "embeddingModel": (self.embedder.loaded if self.settings.embedding_preload else True),
            # TTS is a deliberately optional/degraded path. This check only
            # confirms that an enabled client was constructed; provider health
            # never makes STT or menu recommendation unready.
            "ttsConfiguration": (
                self.settings.effective_tts_provider == "disabled"
                or self.tts_client is not None
            ),
            # Preserve the previous readiness key for existing dashboards.
            "fishTtsConfiguration": (
                self.settings.effective_tts_provider != "fish"
                or self.tts_client is not None
            ),
        }

    def token_verifier(self) -> AccessTokenVerifier:
        return AccessTokenVerifier(
            self.settings.jwt_public_key,
            audience=self.settings.jwt_audience,
            algorithms=self.settings.jwt_algorithms,
            issuer=self.settings.jwt_issuer,
            leeway_seconds=self.settings.jwt_leeway_seconds,
            max_ttl_seconds=self.settings.jwt_max_ttl_seconds,
        )

    def create_speech_client(self) -> ClovaStreamingClient:
        secret = self.settings.clova_secret_key
        if secret is None:
            raise RuntimeError("CLOVA streaming credentials are not configured")
        semantic_epd: dict[str, Any] = {}
        if self.settings.clova_semantic_epd:
            semantic_epd = {
                "skipEmptyText": True,
                "useWordEpd": True,
                "usePeriodEpd": True,
                # This only helps CLOVA generate transcripts. TurnManager owns finalization.
                "gapThreshold": int(self.settings.turn_silence_seconds * 1000),
                "durationThreshold": 20_000,
                "syllableThreshold": 0,
            }
        # Weighted groups from the keyword file's "# weight: N" headers; a
        # headerless group falls back to settings.clova_keyword_weight.
        boosting_keywords = (
            load_clova_keyword_groups(self.settings.clova_keyword_file)
            if self.settings.clova_keyword_boosting_enabled
            else ()
        )
        return ClovaStreamingClient(
            secret_key=secret.get_secret_value(),
            target=self.settings.clova_grpc_target,
            language=self.settings.clova_language,
            semantic_epd=semantic_epd,
            boosting_keywords=boosting_keywords,
            keyword_boosting_weight=self.settings.clova_keyword_weight,
            frame_bytes=self.settings.pcm_frame_bytes,
        )

    def create_vad(self) -> Vad:
        return Vad(self.settings.vad_aggressiveness)
