"""Endpoints REST de control."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from .schemas import (
    AddPhrasesPayload,
    ChangeModePayload,
    OKResponse,
    PhraseOut,
    PushNotificationPayload,
    StatusResponse,
    UpdateConfigPayload,
)

if TYPE_CHECKING:
    from ..controller import Controller
    from ..notifications.overlay import NotificationOverlay
    from ..phrases.repo import PhraseRepo
    from .ws import WSBroadcaster

logger = logging.getLogger(__name__)


@dataclass
class APIState:
    """Estado compartido inyectado en los endpoints.

    Mantiene referencias a los componentes principales. Permite que las
    rutas sean simples y testables por separado del resto del sistema.
    """

    controller: "Controller"
    overlay: "NotificationOverlay"
    phrases: "PhraseRepo"
    broadcaster: "WSBroadcaster"

    async def change_mode(self, mode: str) -> bool:
        if mode not in ("slideshow", "spotify", "mix"):
            raise ValueError(f"Unknown mode: {mode}")
        await self.controller.change_mode(mode, automatic=False)
        self.broadcaster.broadcast("mode_changed", {"mode": mode})
        return True

    async def push_notification(self, message: str, duration: float) -> bool:
        self.overlay.push(message, duration=duration)
        self.broadcaster.broadcast(
            "notification_queued",
            {"message": message, "duration": duration},
        )
        return True

    async def update_config(self, values: dict) -> bool:
        await self.controller.update_config(values)
        self.broadcaster.broadcast("config_updated", {"keys": list(values.keys())})
        return True

    async def add_phrases(self, phrases: list[dict]) -> bool:
        ids = await self.phrases.add_many(phrases)
        self.broadcaster.broadcast(
            "phrases_added",
            {"count": len(ids), "ids": ids},
        )
        return True


def build_router(state: APIState) -> APIRouter:
    """Crea el router con todos los endpoints REST."""
    router = APIRouter()

    @router.get("/api/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        return StatusResponse(
            mode=state.controller.current_mode(),
            is_playing=state.controller.is_playing(),
            brightness=state.controller.brightness(),
            port=state.controller.port(),
            notification_queue_size=state.overlay.queue_size(),
        )

    @router.post("/api/mode", response_model=OKResponse)
    async def post_mode(payload: ChangeModePayload) -> OKResponse:
        try:
            await state.change_mode(payload.mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return OKResponse(detail=f"mode -> {payload.mode}")

    @router.post("/api/notify", response_model=OKResponse)
    async def post_notify(payload: PushNotificationPayload) -> OKResponse:
        await state.push_notification(payload.message, payload.duration)
        return OKResponse(detail="notification queued")

    @router.get("/api/config")
    async def get_config() -> dict:
        return state.controller.config_snapshot()

    @router.patch("/api/config", response_model=OKResponse)
    async def patch_config(payload: UpdateConfigPayload) -> OKResponse:
        try:
            await state.update_config(payload.values)
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return OKResponse()

    @router.get("/api/phrases", response_model=list[PhraseOut])
    async def get_phrases() -> list[PhraseOut]:
        return [PhraseOut(**p.to_dict()) for p in state.phrases.list_active()]

    @router.post("/api/phrases", response_model=OKResponse)
    async def post_phrases(payload: AddPhrasesPayload) -> OKResponse:
        items = [p.model_dump() for p in payload.phrases]
        await state.add_phrases(items)
        return OKResponse(detail=f"inserted {len(items)} phrases")

    @router.delete("/api/phrases/{phrase_id}", response_model=OKResponse)
    async def delete_phrase(phrase_id: int) -> OKResponse:
        deleted = await state.phrases.delete(phrase_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Phrase not found")
        return OKResponse(detail="deleted")

    @router.get("/", include_in_schema=False)
    async def index(request: Request):  # type: ignore[no-untyped-def]
        # Render del template base; los detalles se inyectan desde server.py
        return request.app.state.templates.TemplateResponse(
            request,
            "index.html",
            {
                "mode": state.controller.current_mode(),
                "queue_size": state.overlay.queue_size(),
            },
        )

    return router
