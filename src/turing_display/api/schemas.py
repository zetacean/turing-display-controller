"""Esquemas Pydantic para la API REST y WebSocket."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ModeName = Literal["slideshow", "spotify", "mix"]


class ChangeModePayload(BaseModel):
    """Payload del comando ``change_mode``."""

    mode: ModeName


class PushNotificationPayload(BaseModel):
    """Payload del comando ``push_notification``."""

    message: str = Field(min_length=1, max_length=500)
    duration: float = Field(default=5.0, gt=0.0, le=600.0)


class UpdateConfigPayload(BaseModel):
    """Payload del comando ``update_config``.

    Se valida como mapping genérico de string a string. La validación
    semántica contra ``config.ini`` se hace en :class:`~turing_display.config.Config`.
    """

    values: dict[str, str] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def _no_empty_keys(cls, v: dict[str, str]) -> dict[str, str]:
        for key in v:
            if not key.strip():
                raise ValueError("Config key cannot be empty")
        return v


class PhraseIn(BaseModel):
    """Una frase individual."""

    text: str = Field(min_length=1, max_length=1000)
    author: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=100)


class AddPhrasesPayload(BaseModel):
    """Payload del comando ``add_phrases``."""

    phrases: list[PhraseIn] = Field(min_length=1)


# ---------------------------------------------------------------------- #
# Comandos WebSocket (cliente → servidor)
# ---------------------------------------------------------------------- #
class WSCommand(BaseModel):
    """Comando genérico enviado por el cliente al servidor vía WebSocket."""

    action: Literal["change_mode", "push_notification", "update_config", "add_phrases"]
    payload: dict


# ---------------------------------------------------------------------- #
# Eventos servidor → cliente
# ---------------------------------------------------------------------- #
class WSEvent(BaseModel):
    """Evento genérico emitido por el servidor a todos los clientes WS."""

    event: str
    payload: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------- #
# Respuestas REST
# ---------------------------------------------------------------------- #
class StatusResponse(BaseModel):
    """Estado actual del sistema."""

    mode: str
    is_playing: bool
    brightness: int
    port: str | None
    notification_queue_size: int


class PhraseOut(PhraseIn):
    """Frase tal como se devuelve desde la API."""

    id: int


class OKResponse(BaseModel):
    """Respuesta genérica de éxito."""

    ok: bool = True
    detail: str | None = None
