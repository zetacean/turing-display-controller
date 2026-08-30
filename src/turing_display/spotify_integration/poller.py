"""Hilo que pregunta a Spotify periódicamente qué se está reproduciendo."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Callable, Optional

from .client import SpotifyClient

logger = logging.getLogger(__name__)


class SpotifyPoller:
    """Hilo que llama a :meth:`SpotifyClient.currently_playing` cada N segundos.

    Notifica al ``controller`` cuando el estado de reproducción cambia:
        - De "reproduciendo" a "no reproduciendo" durante más de
          ``idle_timeout_s``: pide al controller cambiar a slideshow.
        - El cambio inverso NO se hace automáticamente (el usuario debe
          pedirlo explícitamente, tal como pide el requisito).
    """

    def __init__(
        self,
        client: SpotifyClient,
        poll_interval_s: float = 5.0,
        idle_timeout_s: float = 30.0,
        on_now_playing: Optional[Callable[[dict[str, Any]], None]] = None,
        on_idle_fallback: Optional[Callable[[], None]] = None,
    ) -> None:
        self._client = client
        self._poll_interval_s = poll_interval_s
        self._idle_timeout_s = idle_timeout_s
        self._on_now_playing = on_now_playing
        self._on_idle_fallback = on_idle_fallback
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_playing_ts: float = 0.0
        self._last_track_id: str | None = None

    def start(self) -> None:
        """Arranca el hilo de polling."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="SpotifyPoller", daemon=True)
        self._thread.start()
        logger.info("SpotifyPoller started")

    def stop(self, timeout: float = 5.0) -> None:
        """Detiene el hilo y espera a que termine."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        """Loop principal del hilo."""
        self._loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._poll_loop())
        finally:
            self._loop.close()

    async def _poll_loop(self) -> None:
        """Una iteración del loop de polling."""
        # Pequeño delay inicial para que el sistema arranque
        if self._stop_event.wait(timeout=1.0):
            return
        while not self._stop_event.is_set():
            try:
                data = await self._client.currently_playing()
            except Exception as e:  # noqa: BLE001 - queremos continuar el poll ante errores transitorios
                logger.warning("Spotify poll error: %s", e)
                if self._stop_event.wait(timeout=self._poll_interval_s):
                    return
                continue

            self._process(data)
            if self._stop_event.wait(timeout=self._poll_interval_s):
                return

    def _process(self, data: dict[str, Any] | None) -> None:
        """Procesa la respuesta y dispara callbacks."""
        now = time.time()
        is_playing = bool(data and data.get("is_playing"))
        track_id = data.get("item", {}).get("id") if data and data.get("item") else None

        if is_playing and data:
            self._last_playing_ts = now
            if track_id and track_id != self._last_track_id:
                self._last_track_id = track_id
                logger.debug("Now playing: %s", track_id)
            if self._on_now_playing is not None:
                try:
                    self._on_now_playing(data)
                except Exception as e:  # noqa: BLE001
                    logger.warning("on_now_playing callback error: %s", e)
        else:
            # No está reproduciendo → verificar idle timeout
            if self._last_playing_ts == 0:
                # Nunca reprodujo nada; no hacer fallback aún
                return
            idle_for = now - self._last_playing_ts
            if idle_for >= self._idle_timeout_s and self._on_idle_fallback is not None:
                logger.info("Spotify idle for %.1fs, triggering fallback", idle_for)
                try:
                    self._on_idle_fallback()
                except Exception as e:  # noqa: BLE001
                    logger.warning("on_idle_fallback callback error: %s", e)
                # Reset para no spamear
                self._last_playing_ts = 0
