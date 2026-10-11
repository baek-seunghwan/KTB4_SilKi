"""Small WebSocket transport helpers shared by the session orchestrator."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel


class WebSocketSender:
    """Serialize concurrent turn/search events without interleaving writes."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._lock = asyncio.Lock()

    async def send_model(self, message: BaseModel) -> None:
        payload = message.model_dump(mode="json", by_alias=True, exclude_none=True)
        await self.send_json(payload)

    async def send_json(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            await self._websocket.send_json(payload)
