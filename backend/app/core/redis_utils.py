"""
Utility per la gestione sicura degli URL Redis.

Problema: le password Redis contenenti caratteri speciali (/, @, :, #, ?, ecc.)
rendono malformato l'URL redis://:PASSWORD@host:port/db, causando errori di parsing
e messaggi di errore fuorvianti nei log.

Caso critico: urlparse("redis://:my/secret@redis:6379/0") fallisce perché la '/'
nella password spezza il parsing — urlparse interpreta 'my' come hostname e
'/secret@redis:6379/0' come path.

Soluzione: safe_redis_url() usa un approccio a due stadi:
1. Tenta urlparse standard (funziona se la password non contiene /)
2. Se urlparse produce un risultato incoerente, usa regex per estrarre i componenti
   e ricostruisce l'URL con la password correttamente URL-encoded.
"""

import logging
import re
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Pattern per estrarre i componenti da un URL Redis potenzialmente malformato.
# Supporta: redis://:password@host:port/db
#           redis://user:password@host:port/db
#           redis://host:port/db (senza credenziali)
# La password può contenere qualsiasi carattere tranne '@' (che termina le credenziali).
# Usiamo l'ultimo '@' come separatore credenziali/host per gestire '@' nella password.
_REDIS_URL_RE = re.compile(
    r"^(?P<scheme>redis(?:s)?|rediss?)://"
    r"(?:(?P<userinfo>[^@]*)@)?"  # userinfo opzionale (tutto prima dell'ultimo @)
    r"(?P<hostport>[^/]*)"  # host:port
    r"(?P<path>/.*)?$",  # /db opzionale
    re.IGNORECASE,
)


def _parse_redis_url_robust(redis_url: str) -> dict:
    """
    Parsa un URL Redis in modo robusto, gestendo password con caratteri speciali.

    Usa l'ultimo '@' come separatore tra credenziali e host, in modo da supportare
    '@' nella password (anche se raro).

    Returns:
        dict con chiavi: scheme, username, password, host, port, db
        Tutti i valori sono stringhe o None.
    """
    # Trova l'ultimo '@' per separare credenziali da host
    # (gestisce '@' nella password)
    scheme_end = redis_url.find("://")
    if scheme_end == -1:
        return {}

    scheme = redis_url[:scheme_end].lower()
    rest = redis_url[scheme_end + 3 :]  # Tutto dopo "://"

    last_at = rest.rfind("@")
    if last_at == -1:
        # Nessuna credenziale
        hostport_db = rest
        username = None
        password = None
    else:
        userinfo = rest[:last_at]
        hostport_db = rest[last_at + 1 :]
        # Separa username:password (la prima ':' è il separatore)
        colon_pos = userinfo.find(":")
        if colon_pos == -1:
            username = userinfo or None
            password = None
        else:
            username = userinfo[:colon_pos] or None
            password = userinfo[colon_pos + 1 :] or None

    # Separa host:port da /db
    slash_pos = hostport_db.find("/")
    if slash_pos == -1:
        hostport = hostport_db
        db = ""
    else:
        hostport = hostport_db[:slash_pos]
        db = hostport_db[slash_pos:]

    # Separa host da port
    colon_pos = hostport.rfind(":")
    if colon_pos != -1:
        host = hostport[:colon_pos]
        port_str = hostport[colon_pos + 1 :]
        try:
            port = int(port_str)
        except ValueError:
            host = hostport
            port = None
    else:
        host = hostport
        port = None

    return {
        "scheme": scheme,
        "username": username,
        "password": password,
        "host": host,
        "port": port,
        "db": db,
    }


def safe_redis_url(redis_url: str) -> str:
    """
    Restituisce un URL Redis con la password correttamente URL-encoded.

    Se la password contiene caratteri speciali (/, @, :, #, ecc.) che rendono
    malformato l'URL, questa funzione li codifica in modo sicuro usando un parser
    robusto che gestisce anche URL già malformati (es. password con /).

    Usa sempre il parser robusto basato su rfind('@') come fonte di verità,
    che gestisce correttamente tutti i casi inclusi password con '/', '@', ':'.

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
        >>> safe_redis_url("redis://:mysecret@redis:6379/0")
        'redis://:mysecret@redis:6379/0'
    """
    if not redis_url:
        return redis_url

    try:
        components = _parse_redis_url_robust(redis_url)
        if not components:
            return redis_url

        password = components.get("password")
        if not password:
            return redis_url

        _warn_if_problematic(password)

        encoded_password = quote(password, safe="")
        username = components.get("username") or ""
        host = components.get("host") or ""
        port = components.get("port")
        scheme = components.get("scheme") or "redis"
        db = components.get("db") or ""

        if username:
            netloc = f"{quote(username, safe='')}:{encoded_password}@{host}"
        else:
            netloc = f":{encoded_password}@{host}"

        if port:
            netloc = f"{netloc}:{port}"

        return f"{scheme}://{netloc}{db}"

    except Exception as exc:
        logger.debug("safe_redis_url: impossibile processare URL Redis: %s", exc)
        return redis_url


def _warn_if_problematic(password: str) -> None:
    """Emette un warning se la password contiene caratteri speciali non URL-safe."""
    _PROBLEMATIC_CHARS = set("/@:#?&=+%")
    if any(c in _PROBLEMATIC_CHARS for c in password):
        logger.warning(
            "REDIS_URL: la password contiene caratteri speciali che potrebbero "
            "causare errori di parsing URL. Applicazione URL-encoding automatico. "
            "Suggerimento: usare una password senza /, @, :, # per evitare problemi."
        )
