# API REST + WebSocket

## REST

| Método | Path | Body / Query |
|---|---|---|
| `GET` | `/` | — (HTML dashboard) |
| `GET` | `/healthz` | — |
| `GET` | `/api/status` | — |
| `POST` | `/api/mode` | `{"mode": "slideshow"\|"spotify"\|"mix"}` |
| `POST` | `/api/notify` | `{"message": "...", "duration": 5}` |
| `GET` | `/api/config` | — |
| `PATCH` | `/api/config` | `{"values": {"display.brightness": "75"}}` |
| `GET` | `/api/phrases` | — |
| `POST` | `/api/phrases` | `{"phrases": [{"text":"...","author":"...","category":"..."}]}` |
| `DELETE` | `/api/phrases/{id}` | — |
| `GET` | `/api/spotify/auth/start` | — (redirect a Spotify) |
| `GET` | `/api/spotify/callback` | `?code=...&state=...` |
| `GET` | `/api/spotify/status` | — |

## WebSocket `/ws`

### Cliente → Servidor

```json
{"action": "change_mode", "payload": {"mode": "spotify"}}
{"action": "push_notification", "payload": {"message": "Hola", "duration": 5}}
{"action": "update_config", "payload": {"values": {"display.brightness": "80"}}}
{"action": "add_phrases", "payload": {"phrases": [{"text":"...", "author":"..."}]}}
```

### Servidor → Cliente (broadcast)

```json
{"event": "ack", "payload": {"action": "change_mode"}}
{"event": "mode_changed", "payload": {"mode": "spotify", "automatic": false}}
{"event": "notification_queued", "payload": {"message": "...", "duration": 5}}
{"event": "phrases_added", "payload": {"count": 3, "ids": [1,2,3]}}
{"event": "config_updated", "payload": {"keys": ["display.brightness"]}}
{"event": "spotify_state", "payload": {"is_playing": true, "track": "..."}}
{"event": "error", "payload": {"detail": "..."}}
```

## Thread safety

- Las acciones REST se ejecutan dentro del event loop de uvicorn.
- Las escrituras al caché de frases están protegidas por `threading.Lock`.
- El `WSBroadcaster` usa `asyncio.run_coroutine_threadsafe` para emitir
  broadcasts desde hilos del display loop.
