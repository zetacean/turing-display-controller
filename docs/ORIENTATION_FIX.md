# Orientación del panel — fix de rotación

## Contexto

El panel Turing Smart Screen 3.5" (USBMONITOR_3_5) usado durante el
desarrollo rota **90° en sentido horario** cualquier frame 320×480 que
se le envíe. Esto significa que el contenido se muestra "girado" en el
panel físico, a menos que se compense en software **antes** del envío.

Esto se confirmó experimentalmente con pruebas de flechas, patrones y
textos en el panel conectado a `COM5` (VID `1A86:PID 5722`).

## Regla de oro (aplicar en todo render que se envía al panel)

| Aspecto del contenido | Qué hacer                                  | Por qué                                         |
| --------------------- | ------------------------------------------ | ----------------------------------------------- |
| **Horizontal** (ancho > alto) | Pre-rotar 90° + **stretch** a 320×480 (fill) | El driver rota 90°; queremos que llene todo el panel sin bandas |
| **Vertical** (alto > ancho)  | Pre-rotar 90° + **letterbox** (bandas izq/der) | El driver rota 90°; queremos que mantenga aspecto con franjas a los lados |

**Truco clave**: pintar el contenido en un canvas con la **orientación
opuesta** a la final, y dejar que el driver lo rote.

- Contenido horizontal final → pintar en canvas horizontal 480×240
  (ancho > alto) → pre-rotar 90° + stretch.
- Contenido vertical final → pintar en canvas vertical 240×320
  (alto > ancho) → pre-rotar 90° + letterbox.

**NO aplicar la regla cuando**: el driver ya respeta las dimensiones
del frame (que NO es el caso aquí).

## Comportamiento esperado en el panel

| Tipo de frame 320×480 enviado        | Cómo se ve en el panel físico           |
| ----------------------------------- | --------------------------------------- |
| Frame con contenido **vertical** (240×320 pre-rotado)   | Vertical, con franjas negras a izquierda y derecha |
| Frame con contenido **horizontal** (480×240 pre-rotado) | Horizontal, ocupando toda la pantalla |

## Solución implementada

La compensación se hace en la capa de **render** (`fit_letterbox` para
el slideshow, `_render_fullscreen` para notificaciones, `_render_now_playing`
y `_render_paused` para Spotify), no en el driver ni en el controller.
Esto mantiene el driver intacto y solo ajusta cómo se pinta cada frame
antes de enviarlo.

### `src/turing_display/display/renderer.py::fit_letterbox`

```python
def fit_letterbox(image, width, height, padding_color=(0, 0, 0)):
    if image.mode != "RGB":
        image = image.convert("RGB")
    src_w, src_h = image.size
    if src_w == 0 or src_h == 0:
        return Image.new("RGB", (width, height), padding_color)

    if src_w > src_h:
        # Landscape: pre-rotar 90 + stretch (fill) - ocupa toda la pantalla
        image = image.rotate(90, expand=True)
        return image.resize((width, height), _RESAMPLE)

    # Portrait: pre-rotar 90 + encajar al ancho (bandas arriba/abajo en
    # el frame 320x480, que tras la rotación del driver quedan a
    # izquierda/derecha del panel).
    image = image.rotate(90, expand=True)
    rot_w, rot_h = image.size
    scale = width / rot_w
    new_w = width
    new_h = int(rot_h * scale)
    resized = image.resize((new_w, new_h), _RESAMPLE)
    canvas = Image.new("RGB", (width, height), padding_color)
    canvas.paste(resized, (0, (height - new_h) // 2))
    return canvas
```

### `src/turing_display/notifications/overlay.py::_render_fullscreen`

La notificación se pinta como una **imagen completa** (no overlay sobre
el slideshow). El texto se pinta en un canvas auxiliar del **tamaño
exacto del texto** (cada línea centrada horizontalmente), se pre-rota
90° con `rotate(90, expand=True)`, y se pega centrado en (160, 240)
del frame 320×480. Tras la rotación del driver, el texto aparece
derecho y centrado en el panel, sin importar la longitud del mensaje.

### `src/turing_display/modes/spotify.py::_render_now_playing` y `_render_paused`

El modo Spotify pinta el contenido en un canvas **horizontal 480×240**
con la carátula (320×320) a la izquierda y los detalles (título,
artista, álbum) a la derecha (área de 150px, offset x=330). Luego
aplica la regla:

```python
# Regla: imagen horizontal → pre-rotar 90 + stretch (fill)
img_rot = img_h.transpose(Image.Transpose.ROTATE_90)
return img_rot.resize((width, height), Image.Resampling.LANCZOS)
```

Esto produce, en el panel físico:
- Carátula arriba (que era la izquierda del frame).
- Detalles abajo (que eran la derecha del frame).
- **Ocupando toda la pantalla** (fill, sin bandas).

#### Bug arreglado: offset del texto

Inicialmente el helper `_draw_centered` solo recibía el ancho del
área de texto (`w`) y centraba el texto dentro de los primeros `w`
píxeles del canvas, lo que hacía que el texto apareciera **encima de
la carátula** (entre x=0 y x=150) en vez de a la derecha
(entre x=330 y x=480).

**Fix**: el helper ahora recibe también el offset horizontal del área
(`area_x`):

```python
def _draw_centered(draw, y, text, font, fill, area_x, area_w):
    """Centra el texto dentro del área [area_x, area_x+area_w]."""
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    x = area_x + (area_w - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
```

Y todas las llamadas pasan `text_x, text_w` (no solo `text_w`).

## Verificación

```bash
# Suite completa
uv run pytest -q

# Verificación visual contra el panel real (COM5)
.venv/Scripts/python.exe -c "
import time
from PIL import Image
from turing_display.display import create_display
from turing_display.display.renderer import fit_letterbox

display = create_display(com_port='COM5')
display.set_brightness(80)
display.screen_on()
for f in ['images/03_vertical.png', 'images/01_gradient.png']:
    img = Image.open(f).convert('RGB')
    display.display_pil_image(fit_letterbox(img, 320, 480))
    time.sleep(5)
display.close_serial()
"
```

Resultado esperado (verificado):

- Vertical `03_vertical.png` (1080×1920) → vertical con franjas a los lados.
- Horizontal `01_gradient.png` (1920×1080) → horizontal ocupando todo.
- Notificaciones → texto derecho y centrado, sin importar la longitud.
- Modo Spotify → carátula arriba, detalles abajo, ocupa toda la pantalla.

## Lo que NO se modificó

- `src/turing_display/display/rev_a.py` — driver intacto (HELLO + transmisión de bitmap).
- `src/turing_display/controller.py` — sin transpose, sin rotación.
- Tests (141 verdes).

## Recordatorio para futuras implementaciones

**SIEMPRE** que se renderice un frame que se enviará al panel Turing
3.5", aplicar la regla:
- Contenido horizontal → pre-rotar 90° + stretch (fill) a 320×480.
- Contenido vertical → pre-rotar 90° + letterbox (bandas izq/der).

Si se pinta directamente en el frame 320×480 sin aplicar la regla, el
contenido saldrá girado 90° en el panel.
