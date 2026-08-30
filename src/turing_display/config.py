"""Carga de configuración desde ``config.ini``."""

from __future__ import annotations

import configparser
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DisplayConfig:
    com_port: str = "AUTO"
    brightness: int = 70
    orientation: str = "portrait"
    reset_on_startup: bool = True


@dataclass
class ModesConfig:
    default_mode: str = "slideshow"
    transition_ms: int = 5000
    mix_image_ms: int = 4000
    mix_phrase_ms: int = 6000


@dataclass
class SpotifyConfig:
    client_id: str = ""
    redirect_uri: str = "http://localhost:8000/api/spotify/callback"
    poll_interval_s: float = 5.0
    idle_timeout_s: float = 30.0
    cache_dir: Path = field(default_factory=lambda: Path("./cache/spotify"))


@dataclass
class PhrasesConfig:
    db_path: Path = field(default_factory=lambda: Path("./data/phrases.db"))


@dataclass
class NotificationsConfig:
    default_duration_s: float = 5.0
    max_queue_size: int = 32


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class PathsConfig:
    images_dir: Path = field(default_factory=lambda: Path("./images"))


@dataclass
class Config:
    """Configuración completa del sistema."""

    display: DisplayConfig = field(default_factory=DisplayConfig)
    modes: ModesConfig = field(default_factory=ModesConfig)
    spotify: SpotifyConfig = field(default_factory=SpotifyConfig)
    phrases: PhrasesConfig = field(default_factory=PhrasesConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    @classmethod
    def from_ini(cls, path: str | Path) -> "Config":
        """Carga la configuración desde un archivo ``.ini``.

        Si el archivo no existe, se devuelve la configuración por defecto
        y se registra una advertencia.
        """
        cfg = cls()
        p = Path(path)
        if not p.exists():
            logger.warning("config.ini not found at %s, using defaults", p)
            return cfg

        parser = configparser.ConfigParser()
        parser.read(p, encoding="utf-8")

        if parser.has_section("display"):
            cfg.display.com_port = parser.get("display", "com_port", fallback="AUTO")
            cfg.display.brightness = parser.getint("display", "brightness", fallback=70)
            cfg.display.orientation = parser.get("display", "orientation", fallback="portrait")
            cfg.display.reset_on_startup = parser.getboolean(
                "display", "reset_on_startup", fallback=True
            )

        if parser.has_section("modes"):
            cfg.modes.default_mode = parser.get("modes", "default_mode", fallback="slideshow")
            cfg.modes.transition_ms = parser.getint("modes", "transition_ms", fallback=5000)
            cfg.modes.mix_image_ms = parser.getint("modes", "mix_image_ms", fallback=4000)
            cfg.modes.mix_phrase_ms = parser.getint("modes", "mix_phrase_ms", fallback=6000)

        if parser.has_section("spotify"):
            cfg.spotify.client_id = parser.get("spotify", "client_id", fallback="")
            cfg.spotify.redirect_uri = parser.get(
                "spotify", "redirect_uri", fallback="http://localhost:8000/api/spotify/callback"
            )
            cfg.spotify.poll_interval_s = parser.getfloat(
                "spotify", "poll_interval_s", fallback=5.0
            )
            cfg.spotify.idle_timeout_s = parser.getfloat("spotify", "idle_timeout_s", fallback=30.0)
            cfg.spotify.cache_dir = Path(
                parser.get("spotify", "cache_dir", fallback="./cache/spotify")
            )

        if parser.has_section("phrases"):
            cfg.phrases.db_path = Path(
                parser.get("phrases", "db_path", fallback="./data/phrases.db")
            )

        if parser.has_section("notifications"):
            cfg.notifications.default_duration_s = parser.getfloat(
                "notifications", "default_duration_s", fallback=5.0
            )
            cfg.notifications.max_queue_size = parser.getint(
                "notifications", "max_queue_size", fallback=32
            )

        if parser.has_section("server"):
            cfg.server.host = parser.get("server", "host", fallback="0.0.0.0")
            cfg.server.port = parser.getint("server", "port", fallback=8000)

        if parser.has_section("paths"):
            cfg.paths.images_dir = Path(parser.get("paths", "images_dir", fallback="./images"))

        return cfg
