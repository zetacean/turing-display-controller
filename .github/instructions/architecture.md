# Arquitectura

`turing-display-controller` es una aplicación Python multiplataforma para
controlar pantallas **Turing Smart Display 3.5" Rev A** por USB-Serial.

## Diagrama de capas

```
FastAPI (HTTP + WS)        ← expone dashboard + REST + WebSocket
   └── Controller          ← estado global, cambio de modo
        ├── Modes
        │    ├── slideshow (PIL + fit_letterbox)
        │    ├── spotify   (carátula + título + artista)
        │    └── mix       (intercala fotos + frases)
        ├── NotificationOverlay (cola FIFO + render)
        ├── PhraseRepo (aiosqlite + caché thread-safe)
        ├── Renderer (PIL fit_letterbox)
        └── Display (LcdCommRevA → pyserial → COM5)

SpotifyPoller (hilo daemon) ← llama a /v1/me/player/currently-playing
                              y dispara fallback automático si hay inactividad
```

## Hilos en ejecución

| Hilo | Responsabilidad |
|---|---|
| **DisplayLoop** | Genera un frame del modo activo, compone overlay, envía al display |
| **SerialWriter** | (implícito) — pyserial escribe directamente desde DisplayLoop |
| **NotificationQueue** | Procesado dentro del DisplayLoop (en cada tick) |
| **WebServer** (uvicorn) | Sirve HTTP + WS |
| **SpotifyPoller** | Polling asíncrono cada `poll_interval_s` |

## Decisiones de diseño

- **Protocolo**: solo Revisión A (Turing 3.5" / UsbPCMonitor), la más común.
- **Spotipy + PKCE**: Authorization Code con `code_verifier` y `code_challenge`.
- **Renderizado**: PIL puro con `ImageOps.pad` para letterbox y `resize` para fill.
- **Persistencia**: `aiosqlite` para no bloquear el loop, con caché thread-safe.
- **Configuración**: `config.ini` plano (sin hot-reload, según preferencia del usuario).
- **Frontend**: Jinja2 + HTMX + JS mínimo, sin build step.
- **Tooling**: `uv` para deps, `ruff` + `ty` para calidad, `PyInstaller` para binarios.

## Stack

- Python 3.12+
- FastAPI 0.115+
- Pillow 11+
- aiosqlite 0.20+
- spotipy 2.24+
- pyserial 3.5+
