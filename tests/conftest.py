"""Mock del puerto serie para tests sin hardware."""

from __future__ import annotations

from collections import deque
from typing import Any


class MockSerial:
    """Replica mínima de :class:`serial.Serial` para tests unitarios.

    Almacena todos los bytes escritos en :attr:`written` y permite
    preconfigurar respuestas en :attr:`read_buffer` para que el driver
    reciba lo que enviaría una pantalla real.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.written = bytearray()
        self.read_buffer: deque = deque()
        self.is_open = True
        self.port = kwargs.get("port", args[0] if args else None)
        self.baudrate = kwargs.get("baudrate", args[1] if len(args) > 1 else 115200)
        self.timeout = kwargs.get("timeout", 1)

    # API usada por el driver ----------------------------------------- #
    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def read(self, size: int = 1) -> bytes:
        out = bytearray()
        for _ in range(size):
            if self.read_buffer:
                out.append(self.read_buffer.popleft())
            else:
                break
        return bytes(out)

    def readall(self) -> bytes:
        return self.read(len(self.read_buffer))

    def reset_input_buffer(self) -> None:
        self.read_buffer.clear()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    # Helpers para tests ---------------------------------------------- #
    def feed(self, data: bytes) -> None:
        """Encola datos para que sean leídos por :meth:`read`."""
        self.read_buffer.extend(data)

    def hexdump(self) -> str:
        """Devuelve un volcado hexadecimal de todo lo escrito."""
        return self.written.hex()
