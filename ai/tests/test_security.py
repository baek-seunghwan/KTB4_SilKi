from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from silki_ai.security import AccessTokenVerifier, TokenValidationError


def _pem_pair(algorithm: str) -> tuple[str, str]:
    if algorithm.startswith("RS"):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    else:
        private_key = ec.generate_private_key(ec.SECP256R1())

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def _claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC).replace(microsecond=0)
    claims: dict[str, object] = {
        "sub": str(uuid4()),
        "storeId": str(uuid4()),
        "aud": ["ai-ws"],
        "iss": "silki-be",
        "exp": now + timedelta(minutes=2),
        "iat": now,
        "jti": str(uuid4()),
    }
    claims.update(overrides)
    return claims


def test_verifies_spring_nimbus_compatible_rs256_token() -> None:
    private_key, public_key = _pem_pair("RS256")
    claims_payload = _claims()
    token = jwt.encode(
        claims_payload,
        private_key,
        algorithm="RS256",
        headers={"typ": "JWT"},
    )
    verifier = AccessTokenVerifier(
        public_key,
        audience="ai-ws",
        algorithms=["RS256"],
        issuer="silki-be",
    )

    claims = verifier.verify(token)

    assert claims.sub == claims_payload["sub"]
    assert claims.store_id == claims_payload["storeId"]
    assert claims.iss == "silki-be"
    assert claims.aud == ["ai-ws"]
    assert jwt.get_unverified_header(token)["alg"] == "RS256"


def test_rejects_wrong_audience_issuer_and_expired_token() -> None:
    private_key, public_key = _pem_pair("RS256")
    verifier = AccessTokenVerifier(public_key, algorithms=["RS256"])

    wrong_audience = jwt.encode(
        _claims(aud=["some-other-service"]), private_key, algorithm="RS256"
    )
    wrong_issuer = jwt.encode(_claims(iss="some-other-service"), private_key, algorithm="RS256")
    expired = jwt.encode(
        _claims(exp=datetime.now(UTC) - timedelta(seconds=1)),
        private_key,
        algorithm="RS256",
    )

    with pytest.raises(TokenValidationError):
        verifier.verify(wrong_audience)
    with pytest.raises(TokenValidationError):
        verifier.verify(wrong_issuer)
    with pytest.raises(TokenValidationError):
        verifier.verify(expired)


@pytest.mark.parametrize("claim", ["sub", "storeId", "aud", "iss", "iat", "exp", "jti"])
def test_rejects_missing_required_claim(claim: str) -> None:
    private_key, public_key = _pem_pair("RS256")
    claims = _claims()
    del claims[claim]
    token = jwt.encode(claims, private_key, algorithm="RS256")

    with pytest.raises(TokenValidationError):
        AccessTokenVerifier(public_key, algorithms=["RS256"]).verify(token)


def test_rejects_multi_audience_and_overlong_token_lifetime() -> None:
    private_key, public_key = _pem_pair("RS256")
    now = datetime.now(UTC).replace(microsecond=0)
    verifier = AccessTokenVerifier(public_key, max_ttl_seconds=180)
    multi_audience = jwt.encode(
        _claims(aud=["ai-ws", "another-service"]),
        private_key,
        algorithm="RS256",
    )
    overlong = jwt.encode(
        _claims(iat=now, exp=now + timedelta(seconds=181)),
        private_key,
        algorithm="RS256",
    )

    with pytest.raises(TokenValidationError):
        verifier.verify(multi_audience)
    with pytest.raises(TokenValidationError):
        verifier.verify(overlong)


@pytest.mark.parametrize(
    "overrides",
    [
        {"sub": "not-an-order-session-uuid"},
        {"storeId": "not-a-store-uuid"},
    ],
)
def test_rejects_non_uuid_session_binding_claims(overrides: dict[str, object]) -> None:
    private_key, public_key = _pem_pair("RS256")
    token = jwt.encode(_claims(**overrides), private_key, algorithm="RS256")

    with pytest.raises(TokenValidationError):
        AccessTokenVerifier(public_key).verify(token)


def test_rejects_algorithm_confusion_and_non_rs256_configuration() -> None:
    _, public_key = _pem_pair("RS256")
    symmetric_token = jwt.encode(
        _claims(), "browser-visible-secret-must-never-be-used", algorithm="HS256"
    )

    verifier = AccessTokenVerifier(public_key, algorithms=["RS256"])
    with pytest.raises(TokenValidationError):
        verifier.verify(symmetric_token)

    with pytest.raises(ValueError, match="RS256"):
        AccessTokenVerifier(public_key, algorithms=["HS256"])
    with pytest.raises(ValueError, match="RS256"):
        AccessTokenVerifier(public_key, algorithms=["ES256"])


def test_rejects_non_rsa_malformed_and_weak_public_keys() -> None:
    _, ec_public_key = _pem_pair("ES256")
    weak_private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    weak_public_key = (
        weak_private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    with pytest.raises(ValueError, match="valid PEM"):
        AccessTokenVerifier("not a PEM key")
    with pytest.raises(ValueError, match="RSA public key"):
        AccessTokenVerifier(ec_public_key)
    with pytest.raises(ValueError, match="2048"):
        AccessTokenVerifier(weak_public_key)


def test_rejects_token_signed_by_a_different_key() -> None:
    attacker_private_key, _ = _pem_pair("RS256")
    _, trusted_public_key = _pem_pair("RS256")
    token = jwt.encode(_claims(), attacker_private_key, algorithm="RS256")

    with pytest.raises(TokenValidationError):
        AccessTokenVerifier(trusted_public_key, algorithms=["RS256"]).verify(token)
