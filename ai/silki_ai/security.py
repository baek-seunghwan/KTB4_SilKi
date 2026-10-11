"""Verification of short-lived Spring-issued AI access tokens."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from silki_ai.config import JWT_ALGORITHM


class TokenClaims(BaseModel):
    """Claims required to open an AI WebSocket session."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", str_strip_whitespace=True)

    sub: str = Field(min_length=1, max_length=256)
    store_id: str = Field(alias="storeId", min_length=1, max_length=128)
    aud: str | list[str]
    exp: datetime
    jti: str = Field(min_length=1, max_length=256)
    iss: str = Field(min_length=1, max_length=256)
    iat: datetime
    nbf: datetime | None = None

    @field_validator("aud")
    @classmethod
    def require_nonempty_audience(cls, value: str | list[str]) -> str | list[str]:
        audiences = [value] if isinstance(value, str) else value
        if not audiences or any(not audience.strip() for audience in audiences):
            raise ValueError("aud must contain at least one non-blank audience")
        return value

    @field_validator("sub", "store_id")
    @classmethod
    def require_spring_uuid_identifiers(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError("order session and store claims must be UUIDs") from exc
        return value

    @property
    def order_session_id(self) -> str:
        """Expose the Spring ``sub`` claim using its domain name."""

        return self.sub


class TokenValidationError(ValueError):
    """Raised when a client token cannot be trusted."""

    def __init__(self, code: str = "authentication_failed") -> None:
        self.code = code
        super().__init__(code)


class AccessTokenVerifier:
    """Validate RS256 JWT access tokens issued by Spring.

    The fixed algorithm is checked in both configuration and the protected token
    header. This prevents algorithm confusion and explicitly excludes symmetric
    secrets from the browser-facing authentication flow.
    """

    def __init__(
        self,
        public_key: str,
        *,
        audience: str = "ai-ws",
        algorithms: Sequence[str] = (JWT_ALGORITHM,),
        issuer: str = "silki-be",
        leeway_seconds: int = 0,
        max_ttl_seconds: int = 180,
    ) -> None:
        if not isinstance(public_key, str) or not public_key.strip():
            raise ValueError("a JWT public key is required")
        normalized = tuple(dict.fromkeys(value.upper() for value in algorithms))
        if normalized != (JWT_ALGORITHM,):
            raise ValueError("JWT verification must use RS256 only")
        if not audience.strip():
            raise ValueError("a JWT audience is required")
        if not issuer.strip():
            raise ValueError("a JWT issuer is required")
        if leeway_seconds < 0:
            raise ValueError("JWT leeway cannot be negative")
        if not 0 < max_ttl_seconds <= 180:
            raise ValueError("JWT maximum TTL must be between 1 and 180 seconds")

        try:
            verification_key = serialization.load_pem_public_key(public_key.encode("utf-8"))
        except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
            raise ValueError("JWT public key must be a valid PEM-encoded RSA public key") from exc
        if not isinstance(verification_key, rsa.RSAPublicKey):
            raise ValueError("JWT public key must be an RSA public key")
        if verification_key.key_size < 2048:
            raise ValueError("JWT RSA public key must be at least 2048 bits")

        self._public_key = verification_key
        self._audience = audience
        self._issuer = issuer
        self._leeway_seconds = leeway_seconds
        self._max_ttl_seconds = max_ttl_seconds

    def verify(self, token: str) -> TokenClaims:
        if not token or not token.strip():
            raise TokenValidationError()

        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm != JWT_ALGORITHM:
                raise TokenValidationError()

            decode_options: dict[str, object] = {
                "algorithms": [JWT_ALGORITHM],
                "audience": self._audience,
                "issuer": self._issuer,
                "leeway": self._leeway_seconds,
                "options": {
                    "require": ["sub", "storeId", "aud", "iss", "iat", "exp", "jti"],
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_iat": True,
                    "verify_exp": True,
                },
            }

            payload = jwt.decode(token, self._public_key, **decode_options)
            claims = TokenClaims.model_validate(payload)
        except TokenValidationError:
            raise
        except (jwt.PyJWTError, ValidationError, TypeError, ValueError) as exc:
            raise TokenValidationError() from exc

        audiences = [claims.aud] if isinstance(claims.aud, str) else claims.aud
        if audiences != [self._audience] or claims.iss != self._issuer:
            # Keep exact service binding as an explicit invariant even though
            # PyJWT already verifies that the configured values are present.
            raise TokenValidationError()
        token_ttl_seconds = (claims.exp - claims.iat).total_seconds()
        if not 0 < token_ttl_seconds <= self._max_ttl_seconds:
            raise TokenValidationError()
        return claims
