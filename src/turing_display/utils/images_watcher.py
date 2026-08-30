"""Observador de cambios en el directorio de imágenes (hot-reload)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch  # noqa: F401

logger = logging.getLogger(__name__)


class ImagesWatcher:
    """Vigila el directorio de imágenes y dispara un callback ante cambios.

    Usa ``watchdog`` para detectar eventos ``created``, ``deleted``,
    ``modified`` y ``moved`` sobre archivos. El callback se invoca una
    sola vez tras un breve debounce para evitar disparos duplicados
    cuando un editor copia el archivo en varios pasos.
    """

    def __init__(
        self, directory: Path | str, on_change: Callable[[], None], debounce_s: float = 0.5
    ) -> None:
        """Inicializa el watcher.

        Parameters
        ----------
        directory : Path | str
            Directorio a vigilar.
        on_change : callable
            Función sin argumentos que se invocará cuando haya cambios.
        debounce_s : float
            Segundos de espera tras el último cambio antes de invocar
            ``on_change`` (por defecto 0.5).
        """
        self._dir = Path(directory)
        self._on_change = on_change
        self._debounce_s = debounce_s
        self._observer = None  # watchdog.observers.Observer (alias de tipo)
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Arranca el observador en un hilo daemon."""
        if self._observer is not None:
            return
        if not self._dir.exists():
            logger.warning("Images dir does not exist: %s (watcher not started)", self._dir)
            return

        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(self._dir), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info("ImagesWatcher started for %s", self._dir)

    def stop(self) -> None:
        """Detiene el observador."""
        if self._observer is None:
            return
        try:
            self._observer.stop()
            self._observer.join(timeout=2.0)
        except Exception as e:  # noqa: BLE001
            logger.warning("Watcher stop error: %s", e)
        self._observer = None

    def _trigger(self) -> None:
        """Programa una llamada a ``on_change`` tras el debounce."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
        try:
            self._on_change()
        except Exception as e:  # noqa: BLE001
            logger.warning("on_change callback failed: %s", e)


class _Handler(FileSystemEventHandler):
    """Handler de watchdog que filtra eventos relevantes."""

    #: Extensiones consideradas imágenes.
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}

    def __init__(self, watcher: ImagesWatcher) -> None:
        super().__init__()
        self._watcher = watcher

    def _is_image(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.IMAGE_EXTS

    # Eventos relevantes
    def on_created(self, event):  # type: ignore[no-untyped-def,override]
        if not event.is_directory and self._is_image(event.src_path):
            logger.debug("Image created: %s", event.src_path)
            self._watcher._trigger()  # noqa: SLF001

    def on_deleted(self, event):  # type: ignore[no-untyped-def,override]
        if not event.is_directory and self._is_image(event.src_path):
            logger.debug("Image deleted: %s", event.src_path)
            self._watcher._trigger()  # noqa: SLF001

    def on_modified(self, event):  # type: ignore[no-untyped-def,override]
        if not event.is_directory and self._is_image(event.src_path):
            logger.debug("Image modified: %s", event.src_path)
            self._watcher._trigger()  # noqa: SLF001

    def on_moved(self, event):  # type: ignore[no-untyped-def,override]
        if not event.is_directory and self._is_image(event.src_path):
            logger.debug("Image moved: %s", event.src_path)
            self._watcher._trigger()  # noqa: SLF001
