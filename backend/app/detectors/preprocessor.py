"""
Preprocessore per deobfuscation e normalizzazione del testo.
Gestisce pattern comuni di offuscamento usati nei report SOC/CTI.
"""

import re
import unicodedata
from typing import Tuple

# Pattern di deobfuscation: (pattern_regex, sostituzione)
_DEOBFUSCATION_RULES = [
    # hxxp/hxxps → http/https
    (re.compile(r"\bhxxps?://", re.IGNORECASE), lambda m: m.group(0).lower().replace("hxxp", "http")),
    # [.] o (.) nei domini/IP → .
    (re.compile(r"\[\.\]|\(\.\)"), lambda m: "."),
    # [:]  nei URL → :
    (re.compile(r"\[:\]"), lambda m: ":"),
    # (at) o [at] nelle email → @
    (re.compile(r"\(at\)|\[at\]", re.IGNORECASE), lambda m: "@"),
    # (dot) o [dot] nelle email/domini → .
    (re.compile(r"\(dot\)|\[dot\]", re.IGNORECASE), lambda m: "."),
    # spazi attorno a @ nelle email → @
    (re.compile(r"\s*@\s*"), lambda m: "@"),
]


def deobfuscate(text: str) -> str:
    """
    Applica le regole di deobfuscation al testo.
    Restituisce il testo normalizzato.
    """
    result = text
    for pattern, replacement in _DEOBFUSCATION_RULES:
        result = pattern.sub(replacement, result)
    return result


def normalize_unicode(text: str) -> str:
    """
    Normalizza il testo Unicode (NFC) e applica casefold per confronti.
    Usato per canonical_value, non per la sostituzione nel testo originale.
    """
    return unicodedata.normalize("NFC", text)


def canonical_ip(value: str) -> str:
    """
    Produce la forma canonica di un indirizzo IP rimuovendo offuscamenti.
    Es: "10[.]0[.]0[.]1" → "10.0.0.1"
    """
    return deobfuscate(value).strip()


def canonical_email(value: str) -> str:
    """
    Produce la forma canonica di un'email rimuovendo offuscamenti e normalizzando.
    Es: "user(at)example(dot)com" → "user@example.com"
    """
    return deobfuscate(value).strip().lower()


def canonical_url(value: str) -> str:
    """
    Produce la forma canonica di un URL rimuovendo offuscamenti.
    Es: "hxxps://example[.]com/path" → "https://example.com/path"
    """
    return deobfuscate(value).strip().lower()


def canonical_hostname(value: str) -> str:
    """
    Produce la forma canonica di un hostname.
    """
    return deobfuscate(value).strip().lower()


def canonical_person(value: str) -> str:
    """
    Produce la forma canonica di un nome persona (casefold, trim, spazi singoli).
    Es: "MARIO  ROSSI" → "mario rossi"
    """
    return " ".join(normalize_unicode(value).casefold().split())


def build_deobfuscated_text(original_text: str) -> Tuple[str, bool]:
    """
    Restituisce (testo_deobfuscato, was_modified).
    Usato per eseguire la detection sia sul testo originale che su quello deobfuscato.
    """
    deobf = deobfuscate(original_text)
    return deobf, deobf != original_text
