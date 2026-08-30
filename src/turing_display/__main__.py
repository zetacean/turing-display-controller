"""Punto de entrada principal: ``python -m turing_display``."""

from __future__ import annotations

import asyncio
import logging
import logging.config
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn

from .api import WSBroadcaster, build_app
from .api.routes import APIState
from .config import Config
from .controller import Controller
from .display import create_display
from .modes import MixMode, SlideshowMode, SpotifyMode
from .modes.base import RenderContext
from .notifications.overlay import NotificationOverlay
from .phrases import PhraseRepo
from .spotify_integration import SpotifyClient, SpotifyPoller
from .spotify_integration.tokens import TokenStore
from .utils import ImagesWatcher

logger = logging.getLogger(__name__)


# Velocidad del display loop (frames por segundo objetivo).
DEFAULT_FPS = 1.0


def _setup_logging() -> None:
    """Configura logging estructurado para toda la app."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": "INFO",
                },
            },
            "loggers": {
                "turing_display": {"level": "INFO", "handlers": ["console"], "propagate": False},
                "uvicorn": {"level": "INFO"},
            },
            "root": {"level": "WARNING", "handlers": ["console"]},
        }
    )


class Application:
    """Orquesta todos los componentes y arranca el sistema completo."""

    def __init__(self, config_path: Path | None = None) -> None:
        _setup_logging()
        self.cfg = Config.from_ini(config_path or Path("config.ini"))

        # Asegurar directorios
        self.cfg.paths.images_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.phrases.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.spotify.cache_dir.mkdir(parents=True, exist_ok=True)

        # Display
        try:
            self.display = create_display(com_port=self.cfg.display.com_port)
        except Exception as e:  # noqa: BLE001
            logger.error("No se pudo conectar a la pantalla: %s", e)
            logger.warning("Continuando en modo 'simulado' (sin display)")
            self.display = None  # type: ignore[assignment]
        else:
            try:
                self.display.set_brightness(self.cfg.display.brightness)
            except Exception as e:  # noqa: BLE001
                logger.warning("No se pudo ajustar brillo: %s", e)

        # Componentes principales
        self.overlay = NotificationOverlay(
            default_duration=self.cfg.notifications.default_duration_s
        )
        self.broadcaster = WSBroadcaster()

        # Frases (DB async — inicializamos en run())
        self.phrases = PhraseRepo(self.cfg.phrases.db_path)

        # Modos
        width = self.display.display_width if self.display else 320
        height = self.display.display_height if self.display else 480

        self.slideshow = SlideshowMode(
            self.cfg.paths.images_dir,
            transition_ms=self.cfg.modes.transition_ms,
            width=width,
            height=height,
        )
        self.spotify_mode = SpotifyMode(width=width, height=height)
        self.mix_mode = MixMode(
            self.cfg.paths.images_dir,
            self.phrases,
            image_ms=self.cfg.modes.mix_image_ms,
            phrase_ms=self.cfg.modes.mix_phrase_ms,
            width=width,
            height=height,
        )

        # Controller
        if self.display is not None:
            self.controller = Controller(
                display=self.display,
                modes={
                    "slideshow": self.slideshow,
                    "spotify": self.spotify_mode,
                    "mix": self.mix_mode,
                },
                overlay=self.overlay,
                broadcaster=self.broadcaster,
                default_mode=self.cfg.modes.default_mode,
                images_dir=self.cfg.paths.images_dir,
                phrases_repo=self.phrases,
            )
            self.controller.set_port(
                self.display.com_port if hasattr(self.display, "com_port") else None
            )
        else:
            # Modo sin display: controller con display=None no es posible.
            # Creamos un wrapper mínimo que acepta frames y los descarta.
            self.controller = Controller(
                display=_NullDisplay(width, height),
                modes={
                    "slideshow": self.slideshow,
                    "spotify": self.spotify_mode,
                    "mix": self.mix_mode,
                },
                overlay=self.overlay,
                broadcaster=self.broadcaster,
                default_mode=self.cfg.modes.default_mode,
                images_dir=self.cfg.paths.images_dir,
                phrases_repo=self.phrases,
            )

        # Spotify
        self.spotify_client: SpotifyClient | None = None
        self.spotify_poller: SpotifyPoller | None = None
        if self.cfg.spotify.client_id:
            token_store = TokenStore(self.cfg.phrases.db_path.parent / "spotify_tokens.db")
            self.spotify_client = SpotifyClient(
                client_id=self.cfg.spotify.client_id,
                redirect_uri=self.cfg.spotify.redirect_uri,
                token_store=token_store,
            )

            self.spotify_poller = SpotifyPoller(
                client=self.spotify_client,
                poll_interval_s=self.cfg.spotify.poll_interval_s,
                idle_timeout_s=self.cfg.spotify.idle_timeout_s,
                on_now_playing=lambda data: self._on_spotify_track(data),
                on_idle_fallback=lambda: self._on_spotify_idle(),
            )

        # API state
        self.api_state = APIState(
            controller=self.controller,
            overlay=self.overlay,
            phrases=self.phrases,
            broadcaster=self.broadcaster,
        )

        # Hilos
        self._loop: asyncio.AbstractEventLoop | None = None
        self._display_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._images_watcher: ImagesWatcher | None = None

    # ------------------------------------------------------------------ #
    # Callbacks de Spotify
    # ------------------------------------------------------------------ #
    def _on_spotify_track(self, data: dict[str, Any]) -> None:
        """Actualiza el modo Spotify con la canción actual."""
        self.spotify_mode.update_track(data)
        self.broadcaster.broadcast(
            "spotify_state",
            {
                "is_playing": data.get("is_playing", False),
                "track": (data.get("item") or {}).get("name"),
            },
        )

    def _on_spotify_idle(self) -> None:
        """Fallback a slideshow cuando Spotify está inactivo mucho tiempo."""
        current = self.controller.current_mode()
        if current == "spotify":
            logger.info("Spotify idle → fallback a slideshow")
            if self._loop is not None:
                asyncio.run_coroutine_threadsafe(
                    self.controller.change_mode("slideshow", automatic=True),
                    self._loop,
                )
            else:
                # Sin loop, llamada sincrónica
                self._loop = asyncio.new_event_loop()
                try:
                    self._loop.run_until_complete(
                        self.controller.change_mode("slideshow", automatic=True)
                    )
                finally:
                    self._loop.close()
                    self._loop = None

    # ------------------------------------------------------------------ #
    # Hot-reload de imágenes
    # ------------------------------------------------------------------ #
    def _on_images_changed(self) -> None:
        """Callback invocado por ``ImagesWatcher`` al detectar cambios."""
        logger.info("Cambios detectados en %s, recargando slideshow", self.cfg.paths.images_dir)
        self.slideshow.reload()
        if isinstance(self.mix_mode, MixMode):
            # Forzar re-entrada al modo mix para que recargue su slideshow interno
            self.mix_mode._slideshow.reload()  # type: ignore[attr-defined]
        self.broadcaster.broadcast("images_changed", {"count": len(self.slideshow.images)})

    def _start_images_watcher(self) -> None:
        """Inicia el observador de cambios en el directorio de imágenes."""
        self._images_watcher = ImagesWatcher(
            directory=self.cfg.paths.images_dir,
            on_change=self._on_images_changed,
        )
        self._images_watcher.start()

    # ------------------------------------------------------------------ #
    # Display loop
    # ------------------------------------------------------------------ #
    def _display_loop(self) -> None:
        """Bucle principal que renderiza y envía frames al display."""
        assert self.display is not None or isinstance(self.controller.display, _NullDisplay)
        ctx = RenderContext(
            width=self.controller.display.display_width,
            height=self.controller.display.display_height,
        )
        interval_s = 1.0 / DEFAULT_FPS

        while not self._stop_event.is_set():
            try:
                # 1. Procesar notificaciones (avanzar/activar)
                self.overlay.tick()

                # 2. Generar frame del modo activo
                mode = self.controller.active_mode()
                if mode is None:
                    time.sleep(interval_s)
                    continue
                frame = mode.tick(ctx)

                # 3. Componer overlay si hay notificación activa
                final = self.overlay.compose(frame)

                # 4. Enviar al display
                self.controller.send_frame(final)
            except Exception as e:  # noqa: BLE001
                logger.exception("Error en display loop: %s", e)
            time.sleep(interval_s)

    # ------------------------------------------------------------------ #
    # Run / shutdown
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Arranca el sistema completo."""
        # Inicializar frases (async)
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self.phrases.init())
            self.phrases.attach_loop(self._loop)
        except Exception as e:  # noqa: BLE001
            logger.error("No se pudo inicializar la DB de frases: %s", e)
            self._loop.close()
            self._loop = None

        # Inicializar TokenStore de Spotify (crea la tabla si no existe)
        if self.spotify_client is not None and self._loop is not None:
            try:
                self._loop.run_until_complete(self.spotify_client.init_token_store())
            except Exception as e:  # noqa: BLE001
                logger.error("No se pudo inicializar la DB de tokens de Spotify: %s", e)

        # Arranca hot-reload de imágenes
        self._start_images_watcher()

        # Arranca Spotify poller si hay cliente
        if self.spotify_poller is not None:
            self.spotify_poller.start()

        # Arranca display loop en hilo
        if self.display is not None or isinstance(self.controller.display, _NullDisplay):
            self._display_thread = threading.Thread(
                target=self._display_loop, name="DisplayLoop", daemon=True
            )
            self._display_thread.start()

        # Arranca servidor FastAPI (bloquea hasta shutdown)
        app = build_app(self.api_state, spotify_client=self.spotify_client)

        config = uvicorn.Config(
            app=app,
            host=self.cfg.server.host,
            port=self.cfg.server.port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        # Manejo de señales para shutdown limpio
        stop_event = threading.Event()

        def shutdown(*_args: Any) -> None:
            logger.info("Shutdown signal received")
            stop_event.set()
            server.should_exit = True

        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, shutdown)
        else:
            signal.signal(signal.SIGINT, shutdown)

        try:
            server.run()
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Apaga hilos y libera recursos."""
        logger.info("Apagando sistema...")
        self._stop_event.set()
        if self._images_watcher is not None:
            self._images_watcher.stop()
        if self._display_thread is not None:
            self._display_thread.join(timeout=3.0)
        if self.spotify_poller is not None:
            self.spotify_poller.stop()
        if self.spotify_client is not None:
            try:
                if self._loop is not None and not self._loop.is_closed():
                    self._loop.run_until_complete(self.spotify_client.close())
            except Exception:  # noqa: BLE001
                pass
        if self.display is not None:
            try:
                self.display.screen_off()
            except Exception:  # noqa: BLE001
                pass
        logger.info("Apagado completo")


class _NullDisplay:
    """Display simulado que descarta frames (modo sin hardware)."""

    def __init__(self, width: int, height: int) -> None:
        self.display_width = width
        self.display_height = height

    def display_pil_image(self, image) -> None:  # type: ignore[no-untyped-def]
        return None

    def set_brightness(self, level: int) -> None:
        return None

    def screen_off(self) -> None:
        return None

    def screen_on(self) -> None:
        return None


def main() -> None:
    """Entry point para ``python -m turing_display``."""
    config_path = Path("config.ini")
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    app = Application(config_path=config_path)
    app.run()


if __name__ == "__main__":
    main()
