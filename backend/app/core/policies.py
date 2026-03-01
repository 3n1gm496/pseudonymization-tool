"""
Gestione dei preset e delle policy di pseudonimizzazione.
Ogni policy è versionata e il suo SHA256 viene incluso nel report.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.schemas import EntityType, PresetName

logger = logging.getLogger(__name__)

# Directory delle policy
POLICIES_DIR = Path(__file__).parent.parent.parent / "config" / "policies"


# ─── Definizione Policy ───────────────────────────────────────────────────────

# Policy predefinite (inline, usate come fallback se i file non esistono)
_DEFAULT_POLICIES: Dict[str, Dict[str, Any]] = {
    PresetName.SOC_LOGS: {
        "name": "SOC Logs",
        "version": "1.0",
        "description": "Preset per log SOC: massima copertura entità di rete, identità e path.",
        "enabled_entity_types": [
            "EMAIL",
            "IPV4",
            "IPV6",
            "URL",
            "HOSTNAME",
            "UPN",
            "LDAP_DN",
            "WINDOWS_SID",
            "UNC_PATH",
            "WINDOWS_PATH",
            "LINUX_PATH",
            "PERSON",
            "LDAP_PERSON",
            "ACCOUNT",
            "USERNAME",
            "CODICE_FISCALE",
            "PARTITA_IVA",
            "PHONE",
            "MAIL_HEADER",
            "DOMAIN_FRAGMENT",
            "CUSTOM",
        ],
        "confidence_threshold": 0.55,
        "ldap_detector_enabled": True,
        "match_surname_only": False,
        "domain_fragments_enabled": True,
        "deobfuscation_enabled": True,
    },
    PresetName.POLICY_DOCS: {
        "name": "Policy Docs",
        "version": "1.0",
        "description": "Preset per documenti di policy: focus su identità, CF/PIVA, contatti.",
        "enabled_entity_types": [
            "EMAIL",
            "URL",
            "HOSTNAME",
            "PERSON",
            "LDAP_PERSON",
            "ACCOUNT",
            "USERNAME",
            "CODICE_FISCALE",
            "PARTITA_IVA",
            "PHONE",
            "CUSTOM",
        ],
        "confidence_threshold": 0.65,
        "ldap_detector_enabled": True,
        "match_surname_only": True,
        "domain_fragments_enabled": False,
        "deobfuscation_enabled": False,
    },
    PresetName.EMAIL_HEADERS: {
        "name": "Email Headers",
        "version": "1.0",
        "description": "Preset per email e header: focus su indirizzi, domini, mail headers.",
        "enabled_entity_types": [
            "EMAIL",
            "IPV4",
            "IPV6",
            "URL",
            "HOSTNAME",
            "UPN",
            "MAIL_HEADER",
            "PERSON",
            "LDAP_PERSON",
            "ACCOUNT",
            "USERNAME",
            "CUSTOM",
        ],
        "confidence_threshold": 0.60,
        "ldap_detector_enabled": True,
        "match_surname_only": False,
        "domain_fragments_enabled": True,
        "deobfuscation_enabled": True,
    },
}


def get_policy(preset: PresetName) -> Dict[str, Any]:
    """
    Restituisce la policy per il preset specificato.
    Prima cerca un file YAML/JSON in config/policies/, poi usa il default inline.
    """
    # Prova a caricare da file
    for ext in ("yaml", "yml", "json"):
        policy_file = POLICIES_DIR / f"{preset.value.lower().replace(' ', '_')}.{ext}"
        if policy_file.exists():
            try:
                if ext == "json":
                    return json.loads(policy_file.read_text(encoding="utf-8"))
                else:
                    try:
                        import yaml

                        return yaml.safe_load(policy_file.read_text(encoding="utf-8"))
                    except ImportError:
                        pass
            except Exception as e:
                logger.warning("Errore nel caricamento della policy '%s': %s", policy_file, e)

    # Fallback al default inline
    return _DEFAULT_POLICIES.get(preset, _DEFAULT_POLICIES[PresetName.SOC_LOGS])


def get_policy_hash(preset: PresetName) -> str:
    """Calcola e restituisce il SHA256 della policy serializzata."""
    policy = get_policy(preset)
    policy_json = json.dumps(policy, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(policy_json.encode("utf-8")).hexdigest()


def get_enabled_entity_types(preset: PresetName) -> List[str]:
    """Restituisce la lista dei tipi di entità abilitati per il preset."""
    policy = get_policy(preset)
    return policy.get("enabled_entity_types", [e.value for e in EntityType])


def get_confidence_threshold(preset: PresetName) -> float:
    """Restituisce la soglia di confidenza minima per il preset."""
    policy = get_policy(preset)
    return policy.get("confidence_threshold", 0.55)


def is_ldap_enabled_for_preset(preset: PresetName) -> bool:
    """Restituisce True se il LDAP detector è abilitato per il preset."""
    policy = get_policy(preset)
    return policy.get("ldap_detector_enabled", True)


def is_deobfuscation_enabled(preset: PresetName) -> bool:
    """Restituisce True se la deobfuscation è abilitata per il preset."""
    policy = get_policy(preset)
    return policy.get("deobfuscation_enabled", True)


def save_default_policies() -> None:
    """Salva le policy di default su disco (solo se non esistono già)."""
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    for preset, policy in _DEFAULT_POLICIES.items():
        policy_file = POLICIES_DIR / f"{preset.value.lower().replace(' ', '_')}.json"
        if not policy_file.exists():
            try:
                policy_file.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
                logger.info("Policy salvata: %s", policy_file.name)
            except Exception as e:
                logger.warning("Impossibile salvare la policy '%s': %s", policy_file, e)
