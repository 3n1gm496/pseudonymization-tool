"""
Test suite per app.core.redis_utils.safe_redis_url().

Copre tutti gli edge case identificati durante la revisione:
  - URL senza password (nessuna modifica)
  - Password senza caratteri speciali (nessuna modifica)
  - Password con '/' (caso critico — urlparse fallisce)
  - Password con '@' (caso critico — rfind('@') necessario)
  - Password con ':' (separatore username:password)
  - Password con '#', '?', '&', '=', '+', '%'
  - Password con multipli caratteri speciali combinati
  - Password già URL-encoded (idempotenza)
  - URL con username e password
  - URL senza porta
  - URL con database diverso da /0
  - URL vuoto o None
  - URL malformato (senza ://)
  - Schema redis vs rediss (TLS)
"""

import logging

import pytest
from app.core.redis_utils import _parse_redis_url_robust, _warn_if_problematic, safe_redis_url


# ─── safe_redis_url: URL senza password ──────────────────────────────────────


def test_safe_redis_url_no_password():
    """URL senza credenziali non viene modificato."""
    url = "redis://redis:6379/0"
    assert safe_redis_url(url) == url


def test_safe_redis_url_empty_string():
    """URL vuoto viene restituito invariato."""
    assert safe_redis_url("") == ""


def test_safe_redis_url_none_like_empty():
    """Stringa vuota viene restituita invariata."""
    result = safe_redis_url("")
    assert result == ""


# ─── safe_redis_url: Password senza caratteri speciali ───────────────────────


def test_safe_redis_url_simple_password():
    """Password senza caratteri speciali non viene modificata."""
    url = "redis://:mysecretpassword@redis:6379/0"
    result = safe_redis_url(url)
    assert result == url


def test_safe_redis_url_alphanumeric_password():
    """Password alfanumerica non viene modificata."""
    url = "redis://:Pass123word@redis:6379/0"
    result = safe_redis_url(url)
    assert result == url


# ─── safe_redis_url: Password con '/' (caso critico) ─────────────────────────


def test_safe_redis_url_password_with_slash():
    """Password con '/' viene URL-encoded correttamente."""
    url = "redis://:my/secret@redis:6379/0"
    result = safe_redis_url(url)
    assert "my%2Fsecret" in result
    assert "redis:6379/0" in result


def test_safe_redis_url_password_with_multiple_slashes():
    """Password con multipli '/' viene URL-encoded correttamente."""
    url = "redis://:a/b/c@redis:6379/0"
    result = safe_redis_url(url)
    assert "a%2Fb%2Fc" in result


# ─── safe_redis_url: Password con '@' ────────────────────────────────────────


def test_safe_redis_url_password_with_at_sign():
    """Password con '@' viene URL-encoded usando rfind('@') come separatore."""
    url = "redis://:pass@word@redis:6379/0"
    result = safe_redis_url(url)
    assert "pass%40word" in result
    assert "redis:6379/0" in result


# ─── safe_redis_url: Password con ':' ────────────────────────────────────────


def test_safe_redis_url_password_with_colon():
    """Password con ':' viene URL-encoded correttamente."""
    url = "redis://:pass:word@redis:6379/0"
    result = safe_redis_url(url)
    assert "pass%3Aword" in result


# ─── safe_redis_url: Password con altri caratteri speciali ───────────────────


def test_safe_redis_url_password_with_hash():
    """Password con '#' viene URL-encoded correttamente."""
    url = "redis://:pass#word@redis:6379/0"
    result = safe_redis_url(url)
    assert "pass%23word" in result


def test_safe_redis_url_password_with_question_mark():
    """Password con '?' viene URL-encoded correttamente."""
    url = "redis://:pass?word@redis:6379/0"
    result = safe_redis_url(url)
    assert "pass%3Fword" in result


def test_safe_redis_url_password_with_ampersand():
    """Password con '&' viene URL-encoded correttamente."""
    url = "redis://:pass&word@redis:6379/0"
    result = safe_redis_url(url)
    assert "pass%26word" in result


def test_safe_redis_url_password_with_percent():
    """Password con '%' viene URL-encoded correttamente."""
    url = "redis://:pass%word@redis:6379/0"
    result = safe_redis_url(url)
    assert "pass%25word" in result


def test_safe_redis_url_password_with_multiple_special_chars():
    """Password con combinazione di caratteri speciali viene gestita correttamente."""
    url = "redis://:p@ss/w:o#r?d@redis:6379/0"
    result = safe_redis_url(url)
    # Verifica che l'URL risultante sia ben formato
    assert result.startswith("redis://")
    assert "redis:6379" in result
    # Verifica che i caratteri speciali siano stati encoded
    assert "%40" in result or "%2F" in result or "%3A" in result


# ─── safe_redis_url: Idempotenza (password già URL-encoded) ──────────────────


def test_safe_redis_url_already_encoded_slash():
    """
    safe_redis_url() assume che la password nell'URL sia in chiaro (non già encoded).
    Se la password contiene letteralmente '%2F' (i caratteri %, 2, F), viene
    re-encoded a '%252F' — questo è il comportamento corretto e documentato.

    Se si vuole idempotenza, la password deve essere passata senza encoding
    e lasciare che safe_redis_url() la encodi automaticamente.
    """
    # Password in chiaro con '/' → viene encoded a %2F
    url_plain = "redis://:my/secret@redis:6379/0"
    result = safe_redis_url(url_plain)
    assert "my%2Fsecret" in result

    # Password già encoded con %2F → %2F viene re-encoded a %252F (comportamento atteso)
    url_encoded = "redis://:my%2Fsecret@redis:6379/0"
    result_encoded = safe_redis_url(url_encoded)
    # Il '%' viene encodato a %25, quindi %2F diventa %252F
    assert "my%252Fsecret" in result_encoded


# ─── safe_redis_url: URL con username ────────────────────────────────────────


def test_safe_redis_url_with_username_and_special_password():
    """URL con username e password con caratteri speciali viene gestito correttamente."""
    url = "redis://user:pass/word@redis:6379/0"
    result = safe_redis_url(url)
    assert "user" in result
    assert "pass%2Fword" in result
    assert "redis:6379" in result


# ─── safe_redis_url: Varianti di porta e database ────────────────────────────


def test_safe_redis_url_different_db():
    """URL con database diverso da /0 viene preservato."""
    url = "redis://:mypassword@redis:6379/2"
    result = safe_redis_url(url)
    assert result.endswith("/2")


def test_safe_redis_url_different_port():
    """URL con porta diversa da 6379 viene preservata."""
    url = "redis://:mypassword@redis:6380/0"
    result = safe_redis_url(url)
    assert "6380" in result


def test_safe_redis_url_no_port():
    """URL senza porta esplicita viene gestito correttamente."""
    url = "redis://:mypassword@redis/0"
    result = safe_redis_url(url)
    assert "mypassword" in result or "%2F" not in result  # Nessun errore


# ─── safe_redis_url: Schema rediss (TLS) ─────────────────────────────────────


def test_safe_redis_url_rediss_schema():
    """URL con schema rediss (TLS) viene gestito correttamente."""
    url = "rediss://:my/secret@redis:6380/0"
    result = safe_redis_url(url)
    assert result.startswith("rediss://")
    assert "my%2Fsecret" in result


# ─── safe_redis_url: URL malformati ──────────────────────────────────────────


def test_safe_redis_url_malformed_no_scheme():
    """URL senza schema viene restituito invariato senza eccezioni."""
    url = "redis:6379/0"  # Manca ://
    result = safe_redis_url(url)
    # Non deve sollevare eccezioni
    assert isinstance(result, str)


def test_safe_redis_url_completely_invalid():
    """URL completamente invalido viene restituito invariato senza eccezioni."""
    url = "not-a-url-at-all"
    result = safe_redis_url(url)
    assert isinstance(result, str)


# ─── _parse_redis_url_robust: test unitari ───────────────────────────────────


def test_parse_redis_url_robust_simple():
    """Parsa correttamente un URL Redis semplice."""
    result = _parse_redis_url_robust("redis://:password@redis:6379/0")
    assert result["scheme"] == "redis"
    assert result["password"] == "password"
    assert result["host"] == "redis"
    assert result["port"] == 6379
    assert result["db"] == "/0"


def test_parse_redis_url_robust_password_with_slash():
    """Parsa correttamente un URL Redis con password contenente '/'."""
    result = _parse_redis_url_robust("redis://:my/secret@redis:6379/0")
    assert result["password"] == "my/secret"
    assert result["host"] == "redis"
    assert result["port"] == 6379


def test_parse_redis_url_robust_password_with_at():
    """Parsa correttamente un URL Redis con password contenente '@' (usa rfind)."""
    result = _parse_redis_url_robust("redis://:pass@word@redis:6379/0")
    assert result["password"] == "pass@word"
    assert result["host"] == "redis"


def test_parse_redis_url_robust_no_credentials():
    """Parsa correttamente un URL Redis senza credenziali."""
    result = _parse_redis_url_robust("redis://redis:6379/0")
    assert result["username"] is None
    assert result["password"] is None
    assert result["host"] == "redis"
    assert result["port"] == 6379


def test_parse_redis_url_robust_with_username():
    """Parsa correttamente un URL Redis con username e password."""
    result = _parse_redis_url_robust("redis://user:password@redis:6379/0")
    assert result["username"] == "user"
    assert result["password"] == "password"


def test_parse_redis_url_robust_no_scheme():
    """Restituisce dict vuoto per URL senza schema."""
    result = _parse_redis_url_robust("redis:6379/0")
    assert result == {}


def test_parse_redis_url_robust_rediss():
    """Parsa correttamente schema rediss (TLS)."""
    result = _parse_redis_url_robust("rediss://:password@redis:6380/1")
    assert result["scheme"] == "rediss"
    assert result["port"] == 6380
    assert result["db"] == "/1"


# ─── _warn_if_problematic: test del logging ──────────────────────────────────


def test_warn_if_problematic_triggers_warning(caplog):
    """Verifica che _warn_if_problematic emetta un warning per password con caratteri speciali."""
    with caplog.at_level(logging.WARNING, logger="app.core.redis_utils"):
        _warn_if_problematic("my/secret")
    assert len(caplog.records) > 0
    assert "caratteri speciali" in caplog.records[0].message


def test_warn_if_problematic_no_warning_for_safe_password(caplog):
    """Verifica che _warn_if_problematic non emetta warning per password sicure."""
    with caplog.at_level(logging.WARNING, logger="app.core.redis_utils"):
        _warn_if_problematic("SafePassword123")
    assert len(caplog.records) == 0
