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
- Imagen horizontal: `resize` a pantalla completa.
- Imagen vertical: `ImageOps.pad` con bandas negras.
- `transition_ms` configurable (default 5000 ms).

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
