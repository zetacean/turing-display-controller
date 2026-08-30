"""Tests para el repositorio de frases con SQLite."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from turing_display.phrases import Phrase, PhraseRepo, db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Devuelve una ruta a un DB temporal."""
    return tmp_path / "phrases.db"


@pytest.fixture
async def repo(db_path: Path) -> PhraseRepo:
    """Crea un repositorio inicializado."""
    r = PhraseRepo(db_path)
    await r.init()
    return r


# ---------------------------------------------------------------------- #
# Tests del esquema
# ---------------------------------------------------------------------- #
async def test_init_db_creates_schema(db_path: Path) -> None:
    """``init_db`` crea la tabla si no existe."""
    assert not db_path.exists()
    await db.init_db(db_path)
    assert db_path.exists()


async def test_init_db_idempotent(db_path: Path) -> None:
    """Llamar ``init_db`` dos veces no falla."""
    await db.init_db(db_path)
    await db.init_db(db_path)


# ---------------------------------------------------------------------- #
# Tests del repositorio
# ---------------------------------------------------------------------- #
async def test_repo_init_loads_empty(repo: PhraseRepo) -> None:
    """Un repo nuevo tiene caché vacía."""
    assert len(repo) == 0
    assert repo.list_active() == []


async def test_add_many_assigns_ids(repo: PhraseRepo) -> None:
    """``add_many`` asigna IDs correlativos."""
    ids = await repo.add_many(
        [
            {"text": "Frase 1", "author": "A1"},
            {"text": "Frase 2", "author": "A2", "category": "Cat1"},
        ]
    )
    assert ids == [1, 2]
    assert len(repo) == 2


async def test_added_phrase_appears_in_cache(repo: PhraseRepo) -> None:
    """Las frases añadidas aparecen inmediatamente en el caché."""
    await repo.add_many([{"text": "Hola", "author": "Mundo"}])
    phrases = repo.list_active()
    assert len(phrases) == 1
    assert phrases[0].text == "Hola"
    assert phrases[0].author == "Mundo"
    assert phrases[0].id is not None


async def test_add_validates_text(repo: PhraseRepo) -> None:
    """Frase sin texto lanza ValueError."""
    with pytest.raises(ValueError):
        await repo.add_many([{"text": ""}])
    with pytest.raises(ValueError):
        await repo.add_many([{"author": "Sin texto"}])


async def test_delete_removes_from_cache(repo: PhraseRepo) -> None:
    """``delete`` elimina de DB y de caché."""
    ids = await repo.add_many([{"text": "X"}, {"text": "Y"}])
    assert len(repo) == 2
    assert await repo.delete(ids[0]) is True
    assert len(repo) == 1
    assert repo.list_active()[0].text == "Y"


async def test_delete_nonexistent(repo: PhraseRepo) -> None:
    """``delete`` de ID inexistente devuelve False."""
    assert await repo.delete(9999) is False


async def test_reload_refreshes_cache(db_path: Path) -> None:
    """``reload`` recarga desde DB."""
    repo = PhraseRepo(db_path)
    await repo.init()
    await repo.add_many([{"text": "A"}, {"text": "B"}])

    # Crear nuevo repo sobre el mismo DB
    repo2 = PhraseRepo(db_path)
    await repo2.reload()
    assert len(repo2) == 2
    texts = {p.text for p in repo2.list_active()}
    assert texts == {"A", "B"}


async def test_get_by_id(repo: PhraseRepo) -> None:
    """``get(id)`` recupera una frase específica."""
    ids = await repo.add_many([{"text": "Find me"}])
    p = repo.get(ids[0])
    assert p is not None
    assert p.text == "Find me"


async def test_get_nonexistent(repo: PhraseRepo) -> None:
    """``get`` de ID inexistente devuelve None."""
    assert repo.get(9999) is None


async def test_cache_thread_safety(db_path: Path) -> None:
    """Las lecturas del caché son thread-safe."""
    import threading

    repo = PhraseRepo(db_path)
    await repo.init()
    await repo.add_many([{"text": f"F{i}"} for i in range(10)])

    results: list[int] = []
    lock = threading.Lock()

    def reader() -> None:
        for _ in range(50):
            n = len(repo)
            with lock:
                results.append(n)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(n == 10 for n in results)


async def test_phrase_to_dict() -> None:
    """``Phrase.to_dict`` produce un dict serializable."""
    p = Phrase(id=1, text="Hola", author="A", category="C")
    d = p.to_dict()
    assert d == {"id": 1, "text": "Hola", "author": "A", "category": "C"}


async def test_persistence_across_instances(db_path: Path) -> None:
    """Las frases añadidas persisten tras reiniciar el repo."""
    repo = PhraseRepo(db_path)
    await repo.init()
    await repo.add_many([{"text": "Persistente", "author": "Test"}])

    repo2 = PhraseRepo(db_path)
    await repo2.init()
    assert len(repo2) == 1
    assert repo2.list_active()[0].text == "Persistente"
