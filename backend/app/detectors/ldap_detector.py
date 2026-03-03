"""
LDAP Detector enterprise — v4.0.0

Principi di sicurezza:
- Cache solo in memoria, mai su disco.
- Nessun log di nomi/DN/account.
- Disattivabile via configurazione.
- Connessione solo verso host configurato (no egress esterno).

Performance:
- Token matcher O(1) via set lookup (NO regex per entry).
- Bigram matcher per fullname.
- Paging RFC2696 completo con diagnostica JSON.

Architettura:
- ldap_client.py: LdapClient (connessione, querying, parsing)
- ldap_detector.py: LdapCache (caching, refresh loop), LdapPersonDetector (detection)
"""

import logging
import re
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from app.detectors.base import BaseDetector, RawFinding
from app.detectors.ldap_client import LdapClient, LdapDiagnostics, LdapEntry
from app.models.schemas import EntityType, LdapConfig
from app.parsers.base import TextChunk

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Cache LDAP enterprise
# ─────────────────────────────────────────────────────────────


class LdapCache:
    """
    Cache in memoria degli utenti LDAP.
    Thread-safe, con TTL, refresh automatico e diagnostica.

    Strutture dati per token matching O(1):
    - accounts_set: set di account canonicalizzati
    - fullname_set: set di "nome cognome" canonicalizzati
    - fullname_reverse_map: "cognome nome" -> "nome cognome" (per match invertito)
    - account_to_canonical: account -> canonical fullname (per pseudonimo consistente)
    - fullname_to_original: canonical fullname -> display name originale
    """

    def __init__(self):
        self._entries: List[LdapEntry] = []
        self._accounts_set: Set[str] = set()
        self._fullname_set: Set[str] = set()
        self._fullname_reverse_map: Dict[str, str] = {}
        self._account_to_canonical: Dict[str, str] = {}
        self._last_refresh: float = 0.0
        self._last_diagnostics: Optional[LdapDiagnostics] = None
        self._lock = threading.RLock()
        self._config: Optional[LdapConfig] = None
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def configure(self, config: LdapConfig) -> None:
        with self._lock:
            self._config = config
            if config.enabled:
                self._start_refresh_loop()

    def _start_refresh_loop(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop_event.clear()
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True, name="ldap-refresh")
        self._refresh_thread.start()

    def _refresh_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._do_refresh()
            except Exception as e:
                logger.warning("LDAP refresh fallito: %s", type(e).__name__)
            interval = (self._config.refresh_interval_minutes if self._config else 60) * 60
            self._stop_event.wait(interval)

    def _do_refresh(self) -> LdapDiagnostics:
        """
        Refresh cache utilizzando LdapClient.
        Restituisce diagnostica dettagliata.
        """
        if not self._config or not self._config.enabled:
            return LdapDiagnostics()

        # Crea client e esegui query
        client = LdapClient(self._config)
        entries, diag = client.query_users()

        if diag.error:
            logger.warning("LDAP query fallita: %s", diag.error)
            return diag

        # Costruisci le strutture di lookup O(1)
        accounts_set: Set[str] = set()
        fullname_set: Set[str] = set()
        fullname_reverse_map: Dict[str, str] = {}
        account_to_canonical: Dict[str, str] = {}

        for e in entries:
            if e.cn:
                accounts_set.add(e.cn)
                if e.full_name:
                    account_to_canonical[e.cn] = e.full_name
            if e.full_name:
                fullname_set.add(e.full_name)
            if e.full_name_rev and e.full_name_rev != e.full_name:
                fullname_reverse_map[e.full_name_rev] = e.full_name

        with self._lock:
            self._entries = entries
            self._accounts_set = accounts_set
            self._fullname_set = fullname_set
            self._fullname_reverse_map = fullname_reverse_map
            self._account_to_canonical = account_to_canonical
            self._last_refresh = time.time()
            self._last_diagnostics = diag

        logger.info("LDAP cache: %d utenti, %d pagine, %dms", len(entries), diag.pages_count, diag.elapsed_ms)
        return diag

    # ── Accesso dati ──────────────────────────────────────────

    def get_entries(self) -> List[LdapEntry]:
        with self._lock:
            return list(self._entries)

    def get_lookup_sets(self):
        """Restituisce le strutture di lookup O(1) per il token matcher."""
        with self._lock:
            return (
                self._accounts_set,
                self._fullname_set,
                self._fullname_reverse_map,
                self._account_to_canonical,
            )

    def get_diagnostics(self) -> Optional[dict]:
        with self._lock:
            return self._last_diagnostics.to_dict() if self._last_diagnostics else None

    def refresh_now(self) -> Tuple[bool, str, Optional[dict]]:
        """Forza refresh immediato. Restituisce (success, message, diagnostics)."""
        try:
            diag = self._do_refresh()
            return True, f"Cache aggiornata: {diag.parsed_users_count_total} utenti", diag.to_dict()
        except Exception as e:
            diag = self._last_diagnostics
            return False, f"{type(e).__name__}: {str(e)[:100]}", diag.to_dict() if diag else None

    def test_connection(self) -> Tuple[bool, str, Optional[int], Optional[dict]]:
        """Testa connessione LDAP. Restituisce (success, message, count, diagnostics)."""
        if not self._config or not self._config.enabled:
            return False, "LDAP non configurato o disabilitato", None, None
        try:
            diag = self._do_refresh()
            return True, "Connessione riuscita", diag.parsed_users_count_total, diag.to_dict()
        except Exception as e:
            diag = self._last_diagnostics
            return False, f"{type(e).__name__}: {str(e)[:100]}", None, diag.to_dict() if diag else None

    def stop(self) -> None:
        self._stop_event.set()


# ─────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────

_ldap_cache = LdapCache()
_ldap_config: Optional[LdapConfig] = None


def configure_ldap(config: LdapConfig) -> None:
    global _ldap_config
    _ldap_config = config
    _ldap_cache.configure(config)


def get_ldap_cache() -> LdapCache:
    return _ldap_cache


def get_ldap_config() -> Optional[LdapConfig]:
    return _ldap_config


# ─────────────────────────────────────────────────────────────
# Token matcher O(1) — NO regex per entry
# ─────────────────────────────────────────────────────────────

# Pattern per tokenizzare il testo: mantiene underscore/dot/hyphen nei token
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-\u00C0-\u024F]+", re.UNICODE)


def _tokenize_with_spans(text: str):
    """Restituisce lista di (token_lower, start, end)."""
    return [(m.group(0).casefold(), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


# ─────────────────────────────────────────────────────────────
# Detector
# ─────────────────────────────────────────────────────────────


class LdapPersonDetector(BaseDetector):
    """
    Detector enterprise per account e fullname LDAP.

    - Token matching O(1) via set lookup (NO regex per entry).
    - Case-insensitive NFKC.
    - Bigram per fullname: "Nome Cognome" e "Cognome Nome" → stessa entità.
    - Fallback CN da DN.
    - LDAP_PERSON ha priorità su match singoli nell'overlap resolver.
    """

    def __init__(self, config: Optional[LdapConfig] = None):
        self._config = config or _ldap_config

    @property
    def name(self) -> str:
        return "LdapPersonDetector"

    def _is_enabled(self) -> bool:
        cfg = self._config or _ldap_config
        return cfg is not None and cfg.enabled

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula or not self._is_enabled():
            return []

        accounts_set, fullname_set, fullname_reverse_map, account_to_canonical = _ldap_cache.get_lookup_sets()
        if not accounts_set and not fullname_set:
            return []

        findings: List[RawFinding] = []
        text = chunk.text
        tokens = _tokenize_with_spans(text)

        # ── Account matching (token singolo) ──────────────────
        for tok_lower, start, end in tokens:
            if tok_lower in accounts_set:
                original = text[start:end]
                canonical = account_to_canonical.get(tok_lower, tok_lower)
                findings.append(
                    RawFinding(
                        entity_type=EntityType.ACCOUNT,
                        original_value=original,
                        canonical_value=canonical,
                        source_chunk=chunk,
                        confidence_score=0.92,
                        detector_name=self.name,
                        start_pos=start,
                        end_pos=end,
                    )
                )

        # ── Fullname matching (bigramma) ──────────────────────
        for i in range(len(tokens) - 1):
            tok1_lower, start1, _ = tokens[i]
            tok2_lower, _, end2 = tokens[i + 1]
            bigram = f"{tok1_lower} {tok2_lower}"

            canonical_fn = None
            if bigram in fullname_set:
                canonical_fn = bigram
            elif bigram in fullname_reverse_map:
                canonical_fn = fullname_reverse_map[bigram]

            if canonical_fn:
                original = text[start1:end2]
                findings.append(
                    RawFinding(
                        entity_type=EntityType.LDAP_PERSON,
                        original_value=original,
                        canonical_value=canonical_fn,
                        source_chunk=chunk,
                        confidence_score=0.95,
                        detector_name=self.name,
                        start_pos=start1,
                        end_pos=end2,
                    )
                )

        return findings
