# Notificaciones overlay

## Cola FIFO

```python
overlay.push(message, duration=5.0)
```

Las notificaciones se almacenan en una `queue.Queue` interna y se
procesan en orden estricto de llegada.

## Render del overlay

1. Capa semitransparente negra al 40 % central de la pantalla.
2. Caja blanca semitransparente con texto envuelto.
3. Texto centrado (split por palabras, ajuste por ancho).
4. Sobrevive al frame del modo activo vía `Image.alpha_composite`.

## Sin solapamiento

`overlay_active` flag: mientras una notificación esté activa, no se
procesan nuevas. Cuando expira, se saca la siguiente de la cola.

```python
overlay.tick()  # promueve siguiente si la activa ya expiró
frame = overlay.compose(mode_frame)
```

## Expiración automática

`compose` también expira notificaciones cuyo tiempo haya pasado
aunque no se haya llamado `tick()` (defensa en profundidad).

## API

```http
POST /api/notify
Content-Type: application/json

{"message": "Hola", "duration": 5}
```

```json
{"action": "push_notification", "payload": {"message": "Hola", "duration": 5}}
```

## `force_clear`

```python
overlay.force_clear()  # vacía cola y notificación activa
```
