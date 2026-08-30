"""Repositorio de frases con caché en memoria thread-safe."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import db

logger = logging.getLogger(__name__)


@dataclass
class Phrase:
    """Frase persistida.

    Attributes
    ----------
    id : int | None
        Identificador (asignado por SQLite al insertar).
    text : str
        Texto principal.
    author : str | None
        Autor de la frase.
    category : str | None
        Categoría o etiqueta.
    """

    id: int | None
    text: str
    author: str | None = None
    category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convierte la frase a un dict serializable."""
        return {
            "id": self.id,
            "text": self.text,
            "author": self.author,
            "category": self.category,
        }


class PhraseRepo:
    """Repositorio de frases con caché thread-safe.

    Mantiene un caché en memoria que se carga al inicializar y se
    mantiene sincronizado tras cada operación de escritura. Las
    operaciones de DB se ejecutan en el loop asyncio del caller.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._cache: list[Phrase] = []
        self._by_id: dict[int, Phrase] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Asocia el loop asyncio (necesario para ejecutar queries async)."""
        self._loop = loop

    # ------------------------------------------------------------------ #
    # Inicialización
    # ------------------------------------------------------------------ #
    async def init(self) -> None:
        """Crea el esquema si no existe y carga el caché inicial."""
        await db.init_db(self._db_path)
        rows = await db.load_all_phrases(self._db_path)
        with self._lock:
            self._cache = [Phrase(**row) for row in rows]
            self._by_id = {p.id: p for p in self._cache if p.id is not None}
        logger.info("PhraseRepo inicializado: %d frases en caché", len(self._cache))

    # ------------------------------------------------------------------ #
    # API sincrónica (lectura desde caché)
    # ------------------------------------------------------------------ #
    def list_active(self) -> list[Phrase]:
        """Devuelve una copia inmutable de la lista cacheada."""
        with self._lock:
            return list(self._cache)

    def get(self, phrase_id: int) -> Phrase | None:
        """Busca una frase por ID en el caché."""
        with self._lock:
            return self._by_id.get(phrase_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    # ------------------------------------------------------------------ #
    # API asíncrona (escritura → DB + actualización de caché)
    # ------------------------------------------------------------------ #
    async def add_many(self, items: list[dict[str, Any]]) -> list[int]:
        """Añade un lote de frases a la DB y al caché.

        Parameters
        ----------
        items : list[dict]
            Cada elemento debe tener ``text``; ``author`` y ``category`` opcionales.

        Returns
        -------
        list[int]
            IDs asignados por SQLite en el mismo orden de entrada.
        """
        if not items:
            return []
        # Validación
        for item in items:
            if not item.get("text"):
                raise ValueError("Cada frase debe tener 'text' no vacío")

        ids = await db.insert_phrases(self._db_path, items)

        with self._lock:
            for item, new_id in zip(items, ids, strict=True):
                phrase = Phrase(id=new_id, **item)
                self._cache.append(phrase)
                if new_id is not None:
                    self._by_id[new_id] = phrase

        logger.info("Añadidas %d frases al caché (total: %d)", len(ids), len(self._cache))
        return ids

    async def delete(self, phrase_id: int) -> bool:
        """Elimina una frase por ID."""
        deleted = await db.delete_phrase(self._db_path, phrase_id)
        if deleted:
            with self._lock:
                self._cache = [p for p in self._cache if p.id != phrase_id]
                self._by_id.pop(phrase_id, None)
        return deleted

    async def reload(self) -> None:
        """Recarga el caché desde la base de datos."""
        rows = await db.load_all_phrases(self._db_path)
        with self._lock:
            self._cache = [Phrase(**row) for row in rows]
            self._by_id = {p.id: p for p in self._cache if p.id is not None}
