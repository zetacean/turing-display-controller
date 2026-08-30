"""Controller: orquesta los modos, el render loop y el envío al display."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .api.ws import WSBroadcaster
from .display.base import LcdComm

if TYPE_CHECKING:
    from .modes.base import Mode
    from .notifications.overlay import NotificationOverlay

logger = logging.getLogger(__name__)


class Controller:
    """Orquesta el estado del sistema: modo activo, brillo, etc.

    Mantiene la referencia al driver de display y al overlay de
    notificaciones, gestiona el cambio entre modos (slideshow, spotify,
    mix) y expone los métodos que llaman los endpoints REST/WS.
    """

    def __init__(
        self,
        display: LcdComm,
        modes: dict[str, "Mode"],
        overlay: "NotificationOverlay",
        broadcaster: WSBroadcaster,
        default_mode: str = "slideshow",
        images_dir: str | Path | None = None,
        phrases_repo: object | None = None,
    ) -> None:
        self._display = display
        self._modes = modes
        self._overlay = overlay
        self._broadcaster = broadcaster
        self._images_dir = Path(images_dir) if images_dir else Path("./images")
        self._phrases_repo = phrases_repo
        self._mode_name = default_mode
        self._lock = threading.Lock()
        self._brightness = 70
        self._port: str | None = None

        # Activar el modo inicial
        mode = self._modes.get(self._mode_name)
        if mode is not None:
            mode.on_enter()

    # ------------------------------------------------------------------ #
    # Propiedades públicas
    # ------------------------------------------------------------------ #
    def current_mode(self) -> str:
        with self._lock:
            return self._mode_name

    def is_playing(self) -> bool:
        """Indica si el modo actual 'reproduce' contenido (siempre True)."""
        return True

    def brightness(self) -> int:
        return self._brightness

    def port(self) -> str | None:
        return self._port

    def config_snapshot(self) -> dict:
        """Devuelve un snapshot de la configuración activa."""
        return {
            "display.brightness": str(self._brightness),
            "display.port": self._port or "AUTO",
            "modes.default_mode": self._mode_name,
            "paths.images_dir": str(self._images_dir),
        }

    # ------------------------------------------------------------------ #
    # Cambio de modo
    # ------------------------------------------------------------------ #
    async def change_mode(self, mode: str, automatic: bool = False) -> None:
        """Cambia al modo ``mode``.

        Parameters
        ----------
        mode : str
            ``"slideshow"``, ``"spotify"`` o ``"mix"``.
        automatic : bool
            ``True`` si el cambio lo disparó un evento interno (ej. Spotify
            inactivo). En ese caso el ``previous_mode`` queda en ``None``
            para que el sistema NO vuelva automáticamente al modo previo
            cuando el evento se revierta.
        """
        if mode not in self._modes:
            raise ValueError(f"Unknown mode: {mode}")

        with self._lock:
            if mode == self._mode_name:
                return
            old_mode = self._mode_name
            self._mode_name = mode

        # Notificar salida/entrada fuera del lock
        old = self._modes.get(old_mode)
        if old is not None:
            try:
                old.on_exit()
            except Exception as e:  # noqa: BLE001
                logger.warning("Error exiting mode %s: %s", old_mode, e)

        new = self._modes[mode]
        try:
            new.on_enter()
        except Exception as e:  # noqa: BLE001
            logger.warning("Error entering mode %s: %s", mode, e)

        logger.info("Mode changed: %s -> %s (automatic=%s)", old_mode, mode, automatic)
        self._broadcaster.broadcast("mode_changed", {"mode": mode, "automatic": automatic})

    # ------------------------------------------------------------------ #
    # Display helpers
    # ------------------------------------------------------------------ #
    def send_frame(self, image) -> None:  # type: ignore[no-untyped-def]
        """Envía un frame al display.

        El frame debe tener las dimensiones nativas del display
        (320×480 portrait). El driver Rev A se encarga del envío.
        """
        if image is None:
            return
        if image.mode != "RGB":
            image = image.convert("RGB")
        self._display.display_pil_image(image)

    @property
    def display(self) -> LcdComm:
        return self._display

    @property
    def overlay(self) -> "NotificationOverlay":
        return self._overlay

    @property
    def broadcaster(self) -> WSBroadcaster:
        return self._broadcaster

    def active_mode(self) -> Optional["Mode"]:
        """Devuelve el objeto :class:`Mode` activo."""
        with self._lock:
            return self._modes.get(self._mode_name)

    def set_brightness(self, level: int) -> None:
        """Cambia el brillo del display."""
        self._brightness = max(0, min(100, level))
        try:
            self._display.set_brightness(self._brightness)
        except Exception as e:  # noqa: BLE001
            logger.warning("set_brightness failed: %s", e)

    def set_port(self, port: str | None) -> None:
        """Actualiza el puerto activo (informativo)."""
        self._port = port

    async def update_config(self, values: dict) -> None:
        """Aplica cambios de configuración en caliente (best-effort)."""
        for key, value in values.items():
            if key == "display.brightness":
                self.set_brightness(int(value))
            elif key == "display.port":
                self.set_port(str(value))
            elif key == "modes.default_mode":
                await self.change_mode(str(value), automatic=True)
            # Otros keys se aceptan pero no se aplican en caliente
