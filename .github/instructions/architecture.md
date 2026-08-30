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
- **Renderizado**: PIL puro. `fit_letterbox` aplica la regla de orientación
  del panel (ver `.github/instructions/modes.md`). NO usar `ImageOps.pad`
  ni `resize` directo sin pasar por `fit_letterbox`.
- **Persistencia**: `aiosqlite` para no bloquear el loop, con caché thread-safe.
- **Configuración**: `config.ini` plano (sin hot-reload, según preferencia del usuario).

## Reglas invariables del renderer

Estas reglas NO se pueden saltar. Si una falla, el resultado es
imágenes volteadas, cortadas, o acostadas en el panel.

1. **EXIF orientation**: cualquier `Image.open()` que vaya a
   `fit_letterbox` (o a cualquier render que vaya al panel) DEBE
   pasar por `ImageOps.exif_transpose()` ANTES de medir
   dimensiones. Sin esto, las fotos de celular llegan en
   orientación incorrecta.

2. **Pre-rotación 90°**: `fit_letterbox` aplica `rotate(90)` antes
   del resize final porque el driver del panel rota 90° al enviar.
   No "optimizar" esto quitando la rotación pensando que es doble.

3. **Stretch vs letterbox**:
   - Horizontal → `rotate(90)` + `resize(width, height)` (fill).
   - Vertical → `rotate(90)` + resize preservando aspect + letterbox.
   Esta distinción **NO es intercambiable**.

4. **Tests son la especificación**: si `tests/test_renderer.py`
   falla, arreglar el renderer, no el test. Ver `README.md` § Tests.

## Patrones prohibidos

- ❌ `image.size` para decidir orientación sin antes aplicar EXIF.
- ❌ `resize((width, height))` directo sin `rotate(90)` previo.
- ❌ `ImageOps.pad(image, (width, height))` — esa función no rota.
- ❌ Relajar aserciones en `test_renderer.py` para que pasen.
- ❌ Cambiar el config.ini del servicio para evitar entender el fix
  (ej. cambiar `images_dir` en vez de arreglar el código).
- **Frontend**: Jinja2 + HTMX + JS mínimo, sin build step.
- **Tooling**: `uv` para deps, `ruff` + `ty` para calidad, `PyInstaller` para binarios.

## Stack

- Python 3.12+
- FastAPI 0.115+
- Pillow 11+
- aiosqlite 0.20+
- spotipy 2.24+
- pyserial 3.5+
