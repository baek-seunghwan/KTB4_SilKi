"""Authentication for Spring-to-AI internal HTTP calls."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status


async def require_internal_api_key(
    request: Request,
    x_internal_api_key: str | None = Header(default=None),
) -> None:
    settings = request.app.state.container.settings
    expected_secret = settings.internal_api_key
    if expected_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="internal API authentication is not configured",
        )
    expected = expected_secret.get_secret_value()
    if not x_internal_api_key or not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal API credentials",
        )
