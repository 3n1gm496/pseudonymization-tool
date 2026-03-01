"""
Settings & LDAP Configuration Router — Local Pseudonymization Tool v4.0

Flussi:
  - GET/POST /api/settings/state      → persistenza config server-side
  - GET/POST /api/settings/ldap       → config LDAP con diagnostica
  - POST /api/settings/ldap/test      → test connessione LDAP
  - POST /api/settings/ldap/refresh   → refresh cache LDAP
  - GET /api/settings/dictionaries    → status dizionari
  - POST /api/settings/dictionaries/reload → ricarica dizionari
  - GET /api/settings/entity-types    → lista tipi entità
  - GET /api/settings/policies        → lista preset policy
  - GET /api/settings/policies/{name} → dettagli policy specifiche
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import (
    LdapConfig, PresetName, EntityType
)
from app.core.config import CONFIG_DIR
from app.core.policies import get_policy, get_enabled_entity_types
from app.core.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_STATE_FILE = CONFIG_DIR / "state.json"


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


def _scrub_sensitive(value: Any) -> Any:
    """Remove sensitive fields (passwords, secrets, tokens) from dictionaries."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if any(token in key_l for token in ("password", "passphrase", "secret", "token", "api_key", "bind_password")):
                continue
            cleaned[key] = _scrub_sensitive(item)
        return cleaned
    if isinstance(value, list):
        return [_scrub_sensitive(item) for item in value]
    return value


def _audit_event(request: Optional[Request], action: str, **details: Any) -> None:
    """Log audit event with user/IP info."""
    user = "anonymous"
    ip = "unknown"
    if request is not None:
        user = getattr(request.state, "auth_user", "anonymous")
        ip = request.client.host if request.client else "unknown"
    cleaned = _scrub_sensitive(details)
    logger.info("AUDIT action=%s user=%s ip=%s details=%s", action, user, ip, cleaned)


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
        except Exception:
            pass
    return {"mode": "light", "ldap": None, "sessions_metadata": []}


@router.post("/settings/state")
async def save_server_state(state: dict):
    """
    Salva la configurazione lato server (no password, no PII).
    La password LDAP viene rimossa prima del salvataggio.
    """
    safe_state = _scrub_sensitive(state)
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
    """Get current LDAP configuration (password redacted)."""
    from app.detectors.ldap_detector import get_ldap_config as _get, get_ldap_cache
    cfg = _get()
    cache = get_ldap_cache()
    diag = cache.get_diagnostics()
    if not cfg:
        return {"enabled": False, "configured": False, "diagnostics": diag}
    d = cfg.model_dump()
    d.pop("bind_password", None)
    d["configured"] = True
    d["diagnostics"] = diag
    return d


@router.post("/settings/ldap")
async def set_ldap_config(config: LdapConfig):
    """Configure LDAP settings."""
    from app.detectors.ldap_detector import configure_ldap
    configure_ldap(config)
    return {"ok": True, "message": f"LDAP configurato: {config.host}:{config.port}"}


@router.post("/settings/ldap/test")
async def test_ldap():
    """
    Test LDAP connection and return diagnostics.
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


@router.post("/settings/ldap/refresh")
async def refresh_ldap():
    """
    Force LDAP cache refresh and return diagnostics.
    """
    from app.detectors.ldap_detector import get_ldap_cache
    cache = get_ldap_cache()
    success, message, diag = cache.refresh_now()
    return {"ok": success, "message": message, "diagnostics": diag}


# ─── Settings: Entity Types ───────────────────────────────────────────────────

@router.get("/settings/entity-types")
async def get_entity_types():
    """Get list of available entity types."""
    return {
        "entity_types": [
            {"value": et.value, "label": et.value.replace("_", " ").title()}
            for et in EntityType
        ]
    }


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
