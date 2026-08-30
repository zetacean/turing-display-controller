"""Persistencia y ciclo de vida de tokens de Spotify."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS spotify_tokens (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT    NOT NULL,
    refresh_token TEXT,
    expires_at   REAL    NOT NULL,
    scope        TEXT
);
"""


@dataclass
class TokenBundle:
    """Conjunto de tokens de Spotify."""

    access_token: str
    refresh_token: str | None
    expires_at: float  # timestamp UNIX en el que expira access_token

    def is_expired(self, skew: float = 60.0) -> bool:
        """Indica si el ``access_token`` está vencido (con margen de ``skew`` s)."""
        return time.time() >= self.expires_at - skew

    def to_dict(self) -> dict:
        """Serializa a dict (sin campos sensibles omitidos)."""
        return asdict(self)


class TokenStore:
    """Persiste el bundle de tokens en SQLite con un único registro (id=1)."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()

    async def init(self) -> None:
        """Crea la tabla si no existe."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def save(self, bundle: TokenBundle) -> None:
        """Guarda (o reemplaza) el bundle de tokens."""
        with self._lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                await db.execute(
                    """
                    INSERT INTO spotify_tokens (id, access_token, refresh_token, expires_at, scope)
                    VALUES (1, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        access_token = excluded.access_token,
                        refresh_token = excluded.refresh_token,
                        expires_at = excluded.expires_at,
                        scope = excluded.scope
                    """,
                    (
                        bundle.access_token,
                        bundle.refresh_token,
                        bundle.expires_at,
                        None,
                    ),
                )
                await db.commit()

    async def load(self) -> TokenBundle | None:
        """Carga el bundle persistido o devuelve ``None``."""
        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM spotify_tokens WHERE id = 1") as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return TokenBundle(
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            expires_at=row["expires_at"],
        )

    async def clear(self) -> None:
        """Elimina el bundle persistido."""
        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.execute("DELETE FROM spotify_tokens WHERE id = 1")
            await db.commit()

    @staticmethod
    def from_oauth_response(data: dict) -> TokenBundle:
        """Construye un :class:`TokenBundle` desde la respuesta OAuth de Spotify."""
        expires_in = float(data.get("expires_in", 3600))
        return TokenBundle(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=time.time() + expires_in,
        )
