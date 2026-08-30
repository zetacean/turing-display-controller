"""Utilidades auxiliares multiplataforma."""

from .images_watcher import ImagesWatcher
from .ports import get_os_name, iter_serial_ports

__all__ = ["ImagesWatcher", "get_os_name", "iter_serial_ports"]
