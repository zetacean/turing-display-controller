"""Renderer PIL: ajuste de imágenes a la resolución nativa del display."""

from __future__ import annotations

from PIL import Image

from turing_display.display.gradients import happy_background

#: Remuestreo de alta calidad.
_RESAMPLE = Image.Resampling.LANCZOS


def fit_letterbox(
    image: Image.Image,
    width: int,
    height: int,
    padding_color: tuple[int, int, int] | None = None,
    gradient_seed: int = 0,
) -> Image.Image:
    """Ajusta ``image`` a ``width × height`` para el panel Turing 3.5".

    El driver del panel rota 90° el frame ``320×480`` que recibe, por lo
    que la imagen debe pintarse "girada" en el frame para que aparezca
    en su orientación original en el panel.

    Reglas:
        - Imagen **landscape** (ancho > alto): se pre-rota 90° y se hace
          stretch a ``width × height`` (sin bandas, ocupa todo el panel).
        - Imagen **portrait** (alto > ancho): se pre-rota 90° y se
          encaja al ancho ``width`` (bandas arriba/abajo en el frame
          que, tras la rotación del driver, quedan a izquierda/derecha
          del panel).

    Las bandas (en imágenes portrait) usan por defecto un degradado
    "feliz" en vez de negro plano. Se puede forzar un color sólido con
    ``padding_color``.

    Parameters
    ----------
    image : PIL.Image.Image
        Imagen fuente en cualquier formato.
    width : int
        Ancho destino (resolución nativa del display).
    height : int
        Alto destino.
    padding_color : tuple[int, int, int] | None
        Color RGB para las bandas. Si es ``None`` (por defecto) se usa
        un degradado feliz.
    gradient_seed : int
        Semilla para elegir la paleta del degradado. Permite que dos
        fondos consecutivos no sean idénticos.

    Returns
    -------
    PIL.Image.Image
        Imagen ``width × height`` en modo ``RGB``.
    """
    if image.mode != "RGB":
        image = image.convert("RGB")

    src_w, src_h = image.size
    if src_w == 0 or src_h == 0:
        if padding_color is None:
            return happy_background(width, height, seed=gradient_seed)
        return Image.new("RGB", (width, height), padding_color)

    if src_w > src_h:
        # Landscape: pre-rotar 90 + stretch a width x height (FILL, sin bandas).
        # El driver rota 90deg el frame al enviarlo; la imagen queda
        # horizontal y centrada, ocupando todo el panel.
        image = image.rotate(90, expand=True)
        return image.resize((width, height), _RESAMPLE)

    # Portrait: pre-rotar 90 + encajar al ancho (bandas arriba/abajo en el frame).
    # Tras la rotacion del driver esas bandas quedan a izquierda/derecha del panel,
    # y la imagen queda vertical centrada.
    image = image.rotate(90, expand=True)
    rot_w, rot_h = image.size
    scale = width / rot_w
    new_w = width
    new_h = int(rot_h * scale)
    resized = image.resize((new_w, new_h), _RESAMPLE)

    if padding_color is None:
        canvas = happy_background(width, height, seed=gradient_seed)
    else:
        canvas = Image.new("RGB", (width, height), padding_color)
    canvas.paste(resized, (0, (height - new_h) // 2))
    return canvas

    if padding_color is None:
        canvas = happy_background(width, height, seed=gradient_seed)
    else:
        canvas = Image.new("RGB", (width, height), padding_color)
    canvas.paste(resized, (0, (height - new_h) // 2))
    return canvas
