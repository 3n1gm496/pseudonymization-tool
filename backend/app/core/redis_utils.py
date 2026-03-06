"""
Utility per la gestione sicura degli URL Redis.

Problema: le password Redis contenenti caratteri speciali (/, @, :, #, ?, ecc.)
rendono malformato l'URL redis://:PASSWORD@host:port/db, causando errori di parsing
e messaggi di errore fuorvianti nei log.

Soluzione: safe_redis_url() ricostruisce l'URL applicando urllib.parse.quote()
alla sola componente password, garantendo la compatibilità con qualsiasi password.
"""

import logging
from urllib.parse import quote, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Caratteri speciali che causano problemi nel parsing degli URL Redis
_PROBLEMATIC_CHARS = set("/@:#?&=+%")


def safe_redis_url(redis_url: str) -> str:
    """
    Restituisce un URL Redis con la password correttamente URL-encoded.

    Se la password contiene caratteri speciali (/, @, :, #, ecc.) che rendono
    malformato l'URL, questa funzione li codifica in modo sicuro.

    Args:
        redis_url: URL Redis nella forma redis://:password@host:port/db
                   oppure redis://host:port/db (senza password)

    Returns:
        URL Redis con password URL-encoded, pronto per l'uso con redis-py.

    Example:
        >>> safe_redis_url("redis://:my/secret@redis:6379/0")
        'redis://:my%2Fsecret@redis:6379/0'
        >>> safe_redis_url("redis://redis:6379/0")
        'redis://redis:6379/0'
    """
    if not redis_url:
        return redis_url

    try:
        parsed = urlparse(redis_url)
        password = parsed.password

        # Nessuna password → URL invariato
        if not password:
            return redis_url

        # Controlla se la password contiene caratteri problematici
        if any(c in _PROBLEMATIC_CHARS for c in password):
            logger.warning(
                "REDIS_URL: la password contiene caratteri speciali che potrebbero "
                "causare errori di parsing URL. Applicazione URL-encoding automatico. "
                "Suggerimento: usare una password senza /, @, :, # per evitare problemi."
            )

        # URL-encode della password (safe='' codifica tutti i caratteri speciali)
        encoded_password = quote(password, safe="")

        # Ricostruisce netloc con password encoded
        # Formato: [user:]password@host[:port]
        username = parsed.username or ""
        host = parsed.hostname or ""
        port = parsed.port

        if username:
            netloc = f"{quote(username, safe='')}:{encoded_password}@{host}"
        else:
            netloc = f":{encoded_password}@{host}"

        if port:
            netloc = f"{netloc}:{port}"

        safe_url = urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )
        return safe_url

    except Exception as exc:
        # In caso di errore nel parsing, restituisce l'URL originale
        logger.debug("safe_redis_url: impossibile processare URL Redis: %s", exc)
        return redis_url
