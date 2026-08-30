# Protocolo Turing Rev A

## Conexión serie

- **Baudios**: 115200 8N1
- **RTS/CTS**: habilitado (`rtscts=True`)
- **Timeout**: 1 segundo
- **Reintentos**: 10 con 1 s de delay

## HELLO handshake

Enviar 6 bytes `0x45` (Command.HELLO). Respuesta identifica sub-revisión:

| Respuesta | Sub-revisión | Resolución |
|---|---|---|
| `0x01 × 6` | USBMONITOR_3_5 | 320×480 |
| `0x02 × 6` | USBMONITOR_5 | 480×800 |
| `0x03 × 6` | USBMONITOR_7 | 600×1024 |
| sin respuesta | TURING_3_5 | 320×480 |

## Comandos

| Command | Code | Notas |
|---|---|---|
| RESET | 101 | Requiere `time.sleep(5)` y reconexión |
| CLEAR | 102 | Necesita orientation=PORTRAIT antes |
| SCREEN_OFF | 108 | |
| SCREEN_ON | 109 | |
| SET_BRIGHTNESS | 110 | **Invertido**: 0 → 255 (más brillante), 100 → 0 |
| SET_ORIENTATION | 121 | 11 bytes con header + dimensiones |
| SET_MIRROR | 122 | |
| DISPLAY_PIXELS | 195 | Lista de píxeles arbitraria |
| DISPLAY_BITMAP | 197 | Header + datos RGB565 |
| HELLO | 69 | Identifica sub-revisión |

## Formato del comando (6 bytes con coordenadas bit-packed)

```
[0]: x[9:2]
[1]: x[1:0] << 6 | y[9:4]
[2]: y[3:0] << 4 | ex[9:6]
[3]: ex[5:0] << 2 | ey[9:8]
[4]: ey[7:0]
[5]: cmd
```

## Frame de imagen

1. Enviar DISPLAY_BITMAP con header `(0, 0, W-1, H-1)` → 6 bytes.
2. Enviar RGB565 little-endian en chunks de `W × 8` bytes (4 líneas).

## Auto-detección

VID:PID `1A86:5722` o número de serie `USB35INCHIPSV2`.

## Quirks importantes

- **Brillo invertido**: la fórmula es `255 - (level/100)*255`.
- **Clear necesita portrait**: antes de CLEAR hay que poner `Orientation.PORTRAIT`.
- **RESET renumera el puerto**: cerrar y reabrir con 5 s de espera.
- **Sin respuesta HELLO**: los oficiales Turing 3.5" no responden → asumir 320×480.
