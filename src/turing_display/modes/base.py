"""Interfaz de los modos de visualización."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class RenderContext:
    """Contexto inmutable que reciben los modos en cada ``tick``.

    Attributes
    ----------
    width : int
        Ancho nativo del display.
    height : int
        Alto nativo del display.
    """

    width: int
    height: int


class Mode(Protocol):
    """Protocolo que implementan todos los modos (slideshow, spotify, mix).

    Un modo es responsable de producir el ``PIL.Image`` exacto a enviar
    al display en cada ``tick``. El :class:`~turing_display.controller.Controller`
    se encarga de orquestar el bucle y el cambio entre modos.
    """

    name: str

    def on_enter(self) -> None:
        """Notifica al modo que va a ser activado (reset de estado)."""
        ...

    def on_exit(self) -> None:
        """Notifica al modo que va a ser desactivado (liberar recursos)."""
        ...

    def tick(self, ctx: RenderContext) -> Image.Image:
        """Genera el siguiente frame.

        Parameters
        ----------
        ctx : RenderContext
            Contexto con dimensiones del display.

        Returns
        -------
        PIL.Image.Image
            Imagen ``ctx.width × ctx.height`` lista para enviar.
        """
        ...
