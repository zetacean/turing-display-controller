"""PKCE (Proof Key for Code Exchange, RFC 7636) para Authorization Code flow.

Spotify requiere PKCE en aplicaciones sin client_secret (apps públicas).
Este módulo genera ``code_verifier`` y ``code_challenge`` según la norma.
"""

from __future__ import annotations

import base64
import hashlib
import secrets


def generate_code_verifier(length: int = 64) -> str:
    """Genera un ``code_verifier`` aleatorio.

    Parameters
    ----------
    length : int
        Longitud en bytes (de 43 a 128 según RFC 7636). Por defecto 64,
        dando un verifier de ~86 caracteres en base64url.

    Returns
    -------
    str
        Cadena base64url sin padding.
    """
    if not 43 <= length <= 128:
        raise ValueError(f"length must be in [43..128], got {length}")
    return _b64url(secrets.token_bytes(length))


def derive_code_challenge(verifier: str, method: str = "S256") -> str:
    """Deriva el ``code_challenge`` a partir del ``code_verifier``.

    Parameters
    ----------
    verifier : str
        El ``code_verifier`` generado por :func:`generate_code_verifier`.
    method : str
        ``"S256"`` (único método obligatorio por Spotify) o ``"plain"``.

    Returns
    -------
    str
        Cadena base64url sin padding lista para enviar a Spotify.
    """
    if method == "S256":
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return _b64url(digest)
    if method == "plain":
        return verifier
    raise ValueError(f"Unknown PKCE method: {method}")


def _b64url(data: bytes) -> str:
    """Base64url sin padding (RFC 4648 §5)."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
