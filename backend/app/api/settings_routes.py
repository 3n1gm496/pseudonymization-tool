"""
Settings & LDAP Configuration Router — Local Pseudonymization Tool v5.2.1

Flussi:
  - GET/POST /api/settings/state         → persistenza config server-side
  - GET      /api/settings/ldap          → config LDAP (campi sensibili redatti)
  - POST     /api/settings/ldap          → salva config LDAP con validazione campi auth
  - POST     /api/settings/ldap/test     → test connessione LDAP (detector/arricchimento)
  - POST     /api/settings/ldap/test-auth → test autenticazione LDAP con credenziali utente
  - POST     /api/settings/ldap/refresh  → refresh cache LDAP
  - GET      /api/settings/dictionaries  → status dizionari
  - POST     /api/settings/dictionaries/reload → ricarica dizionari
  - GET      /api/settings/entity-types  → lista tipi entità
  - GET      /api/settings/policies      → lista preset policy
  - GET      /api/settings/policies/{name} → dettagli policy specifiche
"""

import json
import logging

from app.core.audit import scrub_sensitive
from app.core.config import STATE_FILE
from app.core.policies import get_enabled_entity_types, get_policy
from app.models.schemas import EntityType, LdapConfig, PresetName
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_STATE_FILE = STATE_FILE

# Campi sensibili che non devono essere restituiti nel GET
_LDAP_SENSITIVE_FIELDS = {"bind_password"}

# Campi auth che vengono parzialmente oscurati nel GET (mostrati come "***" se configurati)
_LDAP_AUTH_PARTIAL_REDACT = {"auth_admin_group_dn", "auth_operator_group_dn"}

# Ruoli validi per auth_default_role
_VALID_ROLES = {"admin", "operator"}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_preset(raw_value: str) -> PresetName:
    """Resolve preset name from user input."""
    value = (raw_value or "").strip()
    for preset in PresetName:
        if preset.value.lower() == value.lower():
            return preset
    raise HTTPException(status_code=400, detail=f"Preset non valido: '{raw_value}'.")


def _redact_ldap_response(cfg: LdapConfig) -> dict:
    """
    Prepara la risposta GET per la configurazione LDAP.

    - Rimuove completamente i campi sensibili (bind_password).
    - Oscura parzialmente i group DN se configurati (mostra solo se presenti,
      non il valore completo, per evitare information disclosure).
    """
    d = cfg.model_dump()
    # Rimuovi completamente la password
    for field in _LDAP_SENSITIVE_FIELDS:
        d.pop(field, None)
    # I group DN sono configurati ma non esposti in chiaro: sostituisci con indicatore
    for field in _LDAP_AUTH_PARTIAL_REDACT:
        if d.get(field):
            d[field] = "***configured***"
    return d


def _validate_ldap_auth_fields(config: LdapConfig) -> None:
    """
    Valida i campi di autenticazione LDAP quando auth_enabled è True.

    Raises:
        HTTPException 422: Se i campi obbligatori per l'auth non sono configurati.
    """
    if not config.auth_enabled:
        return

    errors = []

    # Se auth è abilitato, serve almeno un base DN per la ricerca utenti
    if not config.auth_user_base_dn and not config.base_dn:
        errors.append("auth_user_base_dn o base_dn devono essere configurati quando auth_enabled è True.")

    # Se auth è abilitato, serve il bind di servizio per cercare gli utenti
    if not config.bind_dn:
        errors.append("bind_dn è obbligatorio per l'autenticazione LDAP (necessario per la ricerca utenti).")

    # Valida auth_default_role
    if config.auth_default_role and config.auth_default_role not in _VALID_ROLES:
        errors.append(
            f"auth_default_role deve essere uno tra: {', '.join(_VALID_ROLES)}. "
            f"Ricevuto: '{config.auth_default_role}'."
        )

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Configurazione autenticazione LDAP non valida.", "errors": errors},
        )


# Helper functions moved to app.core.audit module


# ─── Settings: Persistenza server-side ────────────────────────────────────────


@router.get("/settings/state")
async def get_server_state():
    """
    Restituisce la configurazione persistita lato server (no password, no PII).
    """
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            return data
        except Exception as exc:  # nosec B110
            logger.debug("get_server_state: impossibile leggere il file di stato: %s", exc)
    return {"mode": "light", "ldap": None, "sessions_metadata": []}


@router.post("/settings/state")
async def save_server_state(state: dict):
    """
    Salva la configurazione lato server (no password, no PII).
    La password LDAP viene rimossa prima del salvataggio.
    """
    safe_state = scrub_sensitive(state)
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore salvataggio stato: {e}")


# ─── Settings: Dizionari ──────────────────────────────────────────────────────


@router.get("/settings/dictionaries")
async def get_dictionaries_status():
    """List available dictionaries and their status."""
    from app.detectors.dictionary_detector import get_dictionary_detector

    detector = get_dictionary_detector()
    return {"total_terms": detector.loaded_terms_count, "files": 3}


@router.post("/settings/dictionaries/reload")
async def reload_dictionaries():
    """Reload all dictionaries from disk."""
    from app.detectors.dictionary_detector import get_dictionary_detector

    detector = get_dictionary_detector()
    detector.reload()
    return {"total_terms": detector.loaded_terms_count, "message": "Dizionari ricaricati."}


# ─── Settings: LDAP ───────────────────────────────────────────────────────────


@router.get("/settings/ldap")
async def get_ldap_config():
    """
    Restituisce la configurazione LDAP corrente con campi sensibili redatti.

    - bind_password: rimosso completamente dalla risposta.
    - auth_admin_group_dn, auth_operator_group_dn: sostituiti con '***configured***'
      se configurati, per indicarne la presenza senza esporre il valore.
    """
    from app.detectors.ldap_detector import get_ldap_cache
    from app.detectors.ldap_detector import get_ldap_config as _get

    cfg = _get()
    cache = get_ldap_cache()
    diag = cache.get_diagnostics()
    if not cfg:
        return {"enabled": False, "configured": False, "diagnostics": diag}
    d = _redact_ldap_response(cfg)
    d["configured"] = True
    d["diagnostics"] = diag
    return d


@router.post("/settings/ldap")
async def set_ldap_config(config: LdapConfig):
    """
    Salva la configurazione LDAP.

    Esegue la validazione dei campi di autenticazione se auth_enabled è True:
    - Verifica che auth_user_base_dn o base_dn siano configurati.
    - Verifica che bind_dn sia presente (necessario per la ricerca utenti al login).
    - Verifica che auth_default_role sia un valore valido ('admin' o 'operator').
    """
    _validate_ldap_auth_fields(config)
    from app.detectors.ldap_detector import configure_ldap

    configure_ldap(config)
    return {"ok": True, "message": f"LDAP configurato: {config.host}:{config.port}"}


@router.post("/settings/ldap/test")
async def test_ldap():
    """
    Testa la connessione LDAP per l'arricchimento dati (detector).
    Verifica che il bind di servizio funzioni e che la ricerca utenti restituisca risultati.
    """
    from app.detectors.ldap_detector import get_ldap_cache

    cache = get_ldap_cache()
    success, message, count, diag = cache.test_connection()
    return {
        "ok": success,
        "error": None if success else message,
        "user_count": count,
        "diagnostics": diag,
    }


class LdapAuthTestRequest(BaseModel):
    """Corpo della richiesta per il test di autenticazione LDAP."""

    username: str
    password: str


@router.post("/settings/ldap/test-auth")
async def test_ldap_auth(request: LdapAuthTestRequest):
    """
    Testa l'autenticazione LDAP con le credenziali di un utente reale.

    Questo endpoint è distinto da /test (che verifica il detector).
    Esegue l'intero flusso di autenticazione:
    1. Ricerca dell'utente per cn nell'objectClass inetOrgPerson.
    2. Bind con le credenziali dell'utente.
    3. Verifica dell'appartenenza ai gruppi configurati.
    4. Restituzione del ruolo determinato.

    Utile per verificare che la configurazione auth LDAP sia corretta prima
    di abilitarla in produzione.

    Nota: Richiede che auth_enabled sia True nella configurazione LDAP.
    """
    from app.core.ldap_auth import authenticate_ldap
    from app.detectors.ldap_detector import get_ldap_config as _get

    cfg = _get()
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail="LDAP non configurato. Configurare prima le impostazioni LDAP.",
        )
    if not cfg.auth_enabled:
        raise HTTPException(
            status_code=400,
            detail=(
                "Autenticazione LDAP non abilitata. "
                "Abilitare 'auth_enabled' nella configurazione LDAP prima di eseguire il test."
            ),
        )
    if not request.username or not request.password:
        raise HTTPException(
            status_code=422,
            detail="username e password sono obbligatori per il test di autenticazione.",
        )

    role = authenticate_ldap(request.username, request.password)
    if role is not None:
        return {
            "ok": True,
            "authenticated": True,
            "role": role,
            "message": (
                f"Autenticazione LDAP riuscita per l'utente '{request.username}'. " f"Ruolo assegnato: '{role}'."
            ),
        }
    else:
        return {
            "ok": False,
            "authenticated": False,
            "role": None,
            "message": (
                f"Autenticazione LDAP fallita per l'utente '{request.username}'. "
                "Verificare le credenziali, la configurazione LDAP e i log del server."
            ),
        }


@router.post("/settings/ldap/refresh")
async def refresh_ldap():
    """
    Forza il refresh della cache LDAP per l'arricchimento dati (detector).
    """
    from app.detectors.ldap_detector import get_ldap_cache

    cache = get_ldap_cache()
    success, message, diag = cache.refresh_now()
    return {"ok": success, "message": message, "diagnostics": diag}


# ─── Settings: Entity Types ───────────────────────────────────────────────────


@router.get("/settings/entity-types")
async def get_entity_types():
    """Get list of available entity types."""
    return {"entity_types": [{"value": et.value, "label": et.value.replace("_", " ").title()} for et in EntityType]}


# ─── Settings: Policies ───────────────────────────────────────────────────────


@router.get("/settings/policies")
async def get_policies():
    """Get list of available policy presets."""
    return {"presets": [preset.value for preset in PresetName]}


@router.get("/settings/policies/{preset_name}")
async def get_policy_preview(preset_name: str):
    """Get details for a specific policy preset."""
    preset = _resolve_preset(preset_name)
    policy = get_policy(preset)
    enabled = get_enabled_entity_types(preset)
    return {
        "preset": preset.value,
        "description": policy.get("description", ""),
        "confidence_threshold": policy.get("confidence_threshold", 0.0),
        "enabled_entity_types": enabled,
        "entity_count": len(enabled),
    }
