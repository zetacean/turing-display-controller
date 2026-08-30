"""Esquema y operaciones de bajo nivel para SQLite (aiosqlite)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS phrases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    author     TEXT,
    category   TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_phrases_category ON phrases(category);
"""


async def init_db(db_path: Path) -> None:
    """Crea las tablas e índices necesarios."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    logger.debug("DB inicializada en %s", db_path)


async def insert_phrases(db_path: Path, phrases: list[dict[str, Any]]) -> list[int]:
    """Inserta un lote de frases y devuelve los IDs asignados.

    Parameters
    ----------
    db_path : Path
        Ruta del archivo SQLite.
    phrases : list[dict]
        Lista de diccionarios con ``text``, ``author``, ``category``.

    Returns
    -------
    list[int]
        IDs asignados por SQLite, en el mismo orden de entrada.
    """
    ids: list[int] = []
    if not phrases:
        return ids

    async with aiosqlite.connect(str(db_path)) as db:
        cursor = await db.execute("BEGIN")
        try:
            for p in phrases:
                cur = await db.execute(
                    "INSERT INTO phrases (text, author, category) VALUES (?, ?, ?)",
                    (p["text"], p.get("author"), p.get("category")),
                )
                ids.append(cur.lastrowid or 0)
            await db.commit()
        except Exception:
            await db.execute("ROLLBACK")
            raise
        else:
            del cursor  # noqa: F841
    return ids


async def load_all_phrases(db_path: Path) -> list[dict[str, Any]]:
    """Carga todas las frases de la base de datos."""
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, text, author, category FROM phrases ORDER BY id") as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def delete_phrase(db_path: Path, phrase_id: int) -> bool:
    """Elimina una frase por ID. Devuelve ``True`` si existía."""
    async with aiosqlite.connect(str(db_path)) as db:
        cur = await db.execute("DELETE FROM phrases WHERE id = ?", (phrase_id,))
        await db.commit()
        return (cur.rowcount or 0) > 0
