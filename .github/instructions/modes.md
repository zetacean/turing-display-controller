# Modos de visualización

## Interfaz `Mode`

```python
class Mode(Protocol):
    name: str

    def on_enter(self) -> None: ...
    def on_exit(self) -> None: ...
    def tick(ctx: RenderContext) -> Image.Image: ...
```

## Slideshow

- Escanea `paths.images_dir` al activarse.
- Mantiene índice circular.
- `transition_ms` configurable (default 5000 ms).
- **Render**: delega en `src/turing_display/display/renderer.py::fit_letterbox`.

### Regla de orientación (CRÍTICA, NO OMITIR)

El panel Turing Smart Display rota 90° el frame que recibe. Por eso
`fit_letterbox` aplica una regla de oro según la orientación REAL de
la imagen (NO las dimensiones en bruto del JPEG):

| Orientación real | Pre-tratamiento | Resultado en el panel |
|---|---|---|
| Horizontal (ancho > alto) | `rotate(90)` + `resize` (stretch fill) | Horizontal, sin bandas |
| Vertical (alto > ancho)   | `rotate(90)` + resize preservando aspecto + letterbox | Vertical, franjas a izq/der |

**REGLA INVARIABLE**: siempre `rotate(90, expand=True)` ANTES de
medir el aspect ratio. Si te saltas la rotación, las dimensiones
serán engañosas.

**REGLA INVARIABLE**: `fit_letterbox` SIEMPRE llama a
`ImageOps.exif_transpose(image)` antes de medir dimensiones. Sin
esto, las fotos de celular (EXIF 6/8) reportan dimensiones en bruto
que NO coinciden con la orientación real, y la regla se aplica al
revés.

### EXIF orientation (CRÍTICO, NO OMITIR)

`Image.open()` carga el JPEG **sin** aplicar la rotación EXIF. Hay
que llamar `ImageOps.exif_transpose(image)` antes de cualquier
medición de dimensiones o render. Sin esto:

- Foto vertical de celular (EXIF 8): bytes dicen `4080×3060` (horizontal)
  pero visualmente es `3060×4080` (vertical).
- El código la toma como horizontal → aplica stretch fill → la imagen
  sale **acostada** en el panel.

`fit_letterbox` aplica `ImageOps.exif_transpose()` automáticamente.
Cualquier nuevo punto de entrada que renderice fotos debe hacer lo
mismo, o delegar en `fit_letterbox`.

## Spotify

- `SpotifyPoller` actualiza el track en background.
- Renderiza carátula (300px), título, artista, álbum.
- Si no hay track activo → placeholder "Spotify en pausa".
- **Fallback automático**: si no reproduce durante `idle_timeout_s`
  (default 30 s), el Controller cambia a slideshow con `automatic=True`.
- **NO vuelve automáticamente** a Spotify al reanudar música: el usuario
  debe llamar `change_mode(spotify)` por API/WS.

## Mix

- Intercala 1 imagen (`mix_image_ms`) + 1 frase (`mix_phrase_ms`).
- Las frases se ciclan a través de `PhraseRepo.list_active()`.
- Si no hay imágenes: muestra frases igualmente.
- Si no hay frases: muestra imágenes igualmente.

## Cambio de modo

```python
await controller.change_mode(mode: str, automatic: bool = False)
```

- `automatic=True` indica un cambio disparado por evento interno
  (ej. Spotify inactivo). El `Controller` registra este flag para que
  el sistema NO vuelva automáticamente al modo previo cuando el
  evento se revierta.
