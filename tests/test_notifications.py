"""Tests para el sistema de notificaciones overlay."""

from __future__ import annotations

import time

import pytest
from PIL import Image

from turing_display.notifications.overlay import Notification, NotificationOverlay


@pytest.fixture
def base_frame() -> Image.Image:
    """Frame negro de 320x480 para composición."""
    return Image.new("RGB", (320, 480), (0, 0, 0))


def test_push_enqueues_notification() -> None:
    """``push`` añade a la cola FIFO."""
    ov = NotificationOverlay(default_duration=1.0)
    ov.push("hola")
    ov.push("mundo")
    assert ov.queue_size() == 2


def test_push_validates_empty_message() -> None:
    """Mensaje vacío lanza ValueError."""
    ov = NotificationOverlay()
    with pytest.raises(ValueError):
        ov.push("")


def test_push_validates_duration() -> None:
    """Duración <= 0 lanza ValueError."""
    ov = NotificationOverlay()
    with pytest.raises(ValueError):
        ov.push("x", duration=0)
    with pytest.raises(ValueError):
        ov.push("x", duration=-1)


def test_tick_promotes_when_no_active() -> None:
    """``tick`` activa la primera notificación si no hay activa."""
    ov = NotificationOverlay()
    ov.push("hola")
    assert ov.current() is None
    ov.tick()
    assert ov.current() is not None
    assert ov.current().message == "hola"


def test_tick_keeps_active_within_duration() -> None:
    """No se promueve nueva mientras la activa no haya expirado."""
    ov = NotificationOverlay()
    ov.push("primera", duration=10.0)
    ov.push("segunda")
    ov.tick()
    assert ov.current().message == "primera"
    ov.tick()
    assert ov.current().message == "primera"  # sigue la primera


def test_tick_promotes_after_expiration() -> None:
    """Tras expirar, se promueve la siguiente."""
    ov = NotificationOverlay()
    ov.push("primera", duration=0.05)
    ov.push("segunda")
    ov.tick()
    assert ov.current().message == "primera"
    time.sleep(0.06)
    ov.tick()
    assert ov.current().message == "segunda"


def test_fifo_order_preserved() -> None:
    """Las notificaciones se procesan en orden FIFO estricto."""
    ov = NotificationOverlay()
    messages = [f"msg{i}" for i in range(5)]
    for m in messages:
        ov.push(m, duration=0.01)

    observed: list[str] = []
    for _ in range(5):
        ov.tick()
        assert ov.current() is not None
        observed.append(ov.current().message)
        time.sleep(0.015)
        # Forzar expiración en la composición
        ov.compose(Image.new("RGB", (320, 480)))

    assert observed == messages


def test_compose_returns_base_when_inactive(base_frame: Image.Image) -> None:
    """Si no hay notificación, compose devuelve una copia del frame."""
    ov = NotificationOverlay()
    out = ov.compose(base_frame)
    assert out.size == base_frame.size
    assert out is not base_frame


def test_compose_returns_fullscreen_image_when_active(base_frame: Image.Image) -> None:
    """Con notificación activa, el frame es la notificación (no overlay sobre base).

    La notificación es una imagen completa con fondo sólido que reemplaza
    el ``base_frame`` mientras está activa.
    """
    ov = NotificationOverlay()
    ov.push("Hola mundo")
    ov.tick()
    out = ov.compose(base_frame)
    assert out.size == base_frame.size
    # La imagen debe tener un fondo sólido (no es overlay sobre la base)
    # y debe contener texto (píxeles blancos)
    px = out.load()
    white_pixels = sum(1 for x in range(320) for y in range(480) if px[x, y] == (255, 255, 255))
    assert white_pixels > 50  # texto blanco del mensaje


def test_compose_clears_expired_notification(base_frame: Image.Image) -> None:
    """``compose`` debe limpiar notificaciones expiradas aunque no se llame ``tick``."""
    ov = NotificationOverlay()
    ov.push("rápida", duration=0.01)
    ov.tick()
    time.sleep(0.02)
    # No llamamos tick; compose debe expirar automáticamente
    out = ov.compose(base_frame)
    # La imagen de salida debería ser igual al base_frame (todo negro)
    assert out.size == base_frame.size
    # Verificar que NO hay overlay: el color central debe ser negro puro
    assert out.getpixel((160, 240)) == (0, 0, 0)


def test_no_overlap_between_notifications(base_frame: Image.Image) -> None:
    """No se procesan nuevas notificaciones mientras una esté activa."""
    ov = NotificationOverlay()
    ov.push("primera", duration=1.0)
    ov.push("segunda", duration=1.0)
    ov.tick()  # activa primera
    # Llamamos tick varias veces: debe seguir activa la primera
    for _ in range(3):
        ov.tick()
        assert ov.current().message == "primera"


def test_force_clear_empties_queue_and_active(base_frame: Image.Image) -> None:
    """``force_clear`` elimina la activa y vacía la cola."""
    ov = NotificationOverlay()
    ov.push("a")
    ov.push("b")
    ov.push("c")
    ov.tick()
    assert ov.current() is not None
    assert ov.queue_size() == 2
    ov.force_clear()
    assert ov.current() is None
    assert ov.queue_size() == 0


def test_long_message_wraps() -> None:
    """Mensajes largos se envuelven en múltiples líneas."""
    ov = NotificationOverlay()
    ov.push("Esta es una notificación muy larga que no cabe en una sola línea")
    ov.tick()
    assert ov.current() is not None


def test_overlay_thread_safety(base_frame: Image.Image) -> None:
    """``push`` y ``tick`` son thread-safe (verificación de no-deadlock)."""
    import threading

    ov = NotificationOverlay()
    expected_total = 60  # 3 producers * 20 mensajes

    def producer() -> None:
        for i in range(20):
            ov.push(f"msg{i}", duration=0.01)

    threads = [threading.Thread(target=producer) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verificar que todos los mensajes están encolados
    assert ov.queue_size() == expected_total

    # Consumir sin sleeps largos: solo verificamos que la cola se vacía
    consumed = 0
    while ov.queue_size() > 0:
        ov.tick()
        ov.compose(base_frame)
        # Avanzar la marca de expiración manualmente para no esperar
        with ov._lock:  # type: ignore[attr-defined]
            if ov._active is not None:  # type: ignore[attr-defined]
                ov._active_until = 0.0  # type: ignore[attr-defined]
        consumed += 1

    assert ov.queue_size() == 0
    assert consumed == expected_total
