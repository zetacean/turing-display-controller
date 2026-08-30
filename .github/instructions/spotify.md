# Integración con Spotify (PKCE)

## Flujo OAuth

1. Cliente abre `/api/spotify/auth/start`.
2. Servidor genera `code_verifier` + `code_challenge` (SHA-256).
3. Redirige a `https://accounts.spotify.com/authorize?code_challenge=...`.
4. Usuario autoriza en Spotify.
5. Spotify redirige a `/api/spotify/callback?code=...&state=...`.
6. Servidor intercambia `code + code_verifier` por tokens.
7. Tokens se persisten en SQLite (`spotify_tokens` table).

## Scopes

```python
DEFAULT_SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
]
```

## Tokens

- `access_token` expira cada ~3600 s.
- `refresh_token` no expira (salvo revocación).
- La tabla `spotify_tokens` tiene un único registro (`id=1`) con
  `ON CONFLICT DO UPDATE` para rotación.

## Refresh automático

`SpotifyClient._get_valid_token` consulta la expiración con margen de
60 s y refresca con `grant_type=refresh_token` antes de cada llamada.

## Polling

`SpotifyPoller` llama a `/v1/me/player/currently-playing` cada
`poll_interval_s` (default 5 s).

## Fallback automático

Cuando el poller observa inactividad durante `idle_timeout_s`
(default 30 s):

1. Llama al callback `on_idle_fallback`.
2. El `Application._on_spotify_idle` cambia el modo a `slideshow`
   con `automatic=True`.
3. El Controller marca el cambio como automático, por lo que el
   sistema NO vuelve solo a Spotify cuando el usuario reanude la
   música — debe pedirlo explícitamente por API.

## Respuestas 204

Spotify devuelve 204 No Content cuando no hay nada reproduciéndose.
El cliente lo trata como "pausado" sin lanzar error.
