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
"""
import re
import unicodedata
import logging
import threading
import time
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field

from app.detectors.base import BaseDetector, RawFinding
from app.parsers.base import TextChunk
from app.models.schemas import EntityType, LdapConfig

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Normalizzazione NFKC case-insensitive
# ─────────────────────────────────────────────────────────────

def _nfkc(s: str) -> str:
    """Unicode NFKC + strip + casefold."""
    if not s:
        return ''
    return unicodedata.normalize('NFKC', s).strip().casefold()


def canonicalize_account(s: str) -> str:
    """Normalizza un account: NFKC + casefold + mantiene underscore/dot/hyphen."""
    return _nfkc(s)


def canonicalize_person_name(s: str) -> str:
    """Normalizza un nome: NFKC + casefold + collapse spaces."""
    n = _nfkc(s)
    return ' '.join(n.split())


def _parse_cn_from_dn(dn: str) -> str:
    """Estrae il valore del primo RDN cn= da un DN LDAP."""
    if not dn:
        return ''
    for part in dn.split(','):
        part = part.strip()
        if part.lower().startswith('cn='):
            return part[3:].strip()
    return ''


# ─────────────────────────────────────────────────────────────
# Struttura entry normalizzata
# ─────────────────────────────────────────────────────────────

@dataclass
class LdapEntry:
    given_name: str       # givenName canonicalizzato
    surname: str          # sn canonicalizzato
    cn: str               # account canonicalizzato
    full_name: str        # "givenName sn" canonicalizzato
    full_name_rev: str    # "sn givenName" canonicalizzato


# ─────────────────────────────────────────────────────────────
# Diagnostica LDAP
# ─────────────────────────────────────────────────────────────

@dataclass
class LdapDiagnostics:
    scope_used: str = 'SUBTREE'
    filter_used: str = ''
    base_dn_used: str = ''
    paging_used: bool = False
    page_size: int = 0
    pages_count: int = 0
    raw_entries_count_total: int = 0
    parsed_users_count_total: int = 0
    dropped_missing_attrs_count: int = 0
    last_cookie_present: bool = False
    server_result_code: Optional[int] = None
    server_result_description: str = ''
    size_limit_exceeded: bool = False
    time_limit_exceeded: bool = False
    elapsed_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'scope_used': self.scope_used,
            'filter_used': self.filter_used,
            'base_dn_used': self.base_dn_used,
            'paging_used': self.paging_used,
            'page_size': self.page_size,
            'pages_count': self.pages_count,
            'raw_entries_count_total': self.raw_entries_count_total,
            'parsed_users_count_total': self.parsed_users_count_total,
            'dropped_missing_attrs_count': self.dropped_missing_attrs_count,
            'last_cookie_present': self.last_cookie_present,
            'server_result_code': self.server_result_code,
            'server_result_description': self.server_result_description,
            'size_limit_exceeded': self.size_limit_exceeded,
            'time_limit_exceeded': self.time_limit_exceeded,
            'elapsed_ms': self.elapsed_ms,
            'error': self.error,
        }


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
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop,
            daemon=True,
            name='ldap-refresh'
        )
        self._refresh_thread.start()

    def _refresh_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._do_refresh()
            except Exception as e:
                logger.warning('LDAP refresh fallito: %s', type(e).__name__)
            interval = (self._config.refresh_interval_minutes if self._config else 60) * 60
            self._stop_event.wait(interval)

    def _do_refresh(self) -> LdapDiagnostics:
        """
        Fetch LDAP con paging RFC2696 completo.
        Restituisce diagnostica dettagliata (sanitizzata).
        """
        diag = LdapDiagnostics()
        if not self._config or not self._config.enabled:
            return diag

        try:
            import ldap3
        except ImportError:
            logger.warning('ldap3 non installato. LDAP detection disabilitata.')
            diag.error = 'ldap3 non installato'
            return diag

        cfg = self._config
        diag.base_dn_used = cfg.base_dn
        diag.filter_used = cfg.filter or (
            '(|(objectClass=inetOrgPerson)(objectClass=person)'
            '(objectClass=organizationalPerson)(objectClass=user))'
        )
        diag.scope_used = 'SUBTREE'
        diag.paging_used = True
        page_size = min(getattr(cfg, 'page_size', 500), 1000)
        diag.page_size = page_size
        max_entries = getattr(cfg, 'cache_max_entries', 100000)

        # Attributi configurabili con fallback chain
        attr_given = getattr(cfg, 'attr_given', 'givenName') or 'givenName'
        attr_sn = getattr(cfg, 'attr_sn', 'sn') or 'sn'
        attr_account = getattr(cfg, 'attr_account', 'cn') or 'cn'
        attrs = list({attr_given, attr_sn, attr_account,
                      'cn', 'uid', 'sAMAccountName', 'displayName'})

        t0 = time.monotonic()
        entries: List[LdapEntry] = []
        raw_total = 0
        dropped = 0
        pages_count = 0

        try:
            server = ldap3.Server(
                cfg.host,
                port=cfg.port,
                use_ssl=cfg.use_tls,
                get_info=ldap3.NONE,
                connect_timeout=getattr(cfg, 'connect_timeout', 10),
            )
            auto_bind = (
                ldap3.AUTO_BIND_TLS_BEFORE_BIND
                if cfg.starttls
                else ldap3.AUTO_BIND_NO_TLS
            )
            conn_kwargs = {
                'server': server,
                'auto_bind': auto_bind,
                'receive_timeout': getattr(cfg, 'receive_timeout', 60),
            }
            if cfg.bind_dn:
                conn_kwargs['user'] = cfg.bind_dn
                conn_kwargs['password'] = cfg.bind_password
            else:
                conn_kwargs['authentication'] = ldap3.ANONYMOUS

            with ldap3.Connection(**conn_kwargs) as conn:
                try:
                    paged_gen = conn.extend.standard.paged_search(
                        search_base=cfg.base_dn,
                        search_filter=diag.filter_used,
                        search_scope=ldap3.SUBTREE,
                        attributes=attrs,
                        paged_size=page_size,
                        generator=True,
                    )
                    last_cookie = False
                    for ldap_entry in paged_gen:
                        if ldap_entry.get('type') == 'searchResEntry':
                            raw_total += 1
                            if len(entries) >= max_entries:
                                logger.warning(
                                    'LDAP: raggiunto limite cache (%d). '
                                    'Aumentare cache_max_entries.',
                                    max_entries
                                )
                                diag.size_limit_exceeded = True
                                break
                            parsed = self._parse_attrs(
                                ldap_entry.get('attributes', {}),
                                ldap_entry.get('dn', ''),
                                attr_given, attr_sn, attr_account
                            )
                            if parsed:
                                entries.append(parsed)
                            else:
                                dropped += 1
                        elif ldap_entry.get('type') == 'searchResRef':
                            pass  # referral, ignorato
                        # Conta le pagine dai controlli
                        controls = ldap_entry.get('controls', {})
                        if '1.2.840.113556.1.4.319' in controls:
                            pages_count += 1
                            cookie = controls['1.2.840.113556.1.4.319'].get('value', {}).get('cookie', b'')
                            last_cookie = bool(cookie)

                    diag.last_cookie_present = last_cookie
                    if pages_count == 0:
                        pages_count = 1  # almeno una pagina

                except Exception as paged_err:
                    # Fallback: ricerca semplice senza paging
                    logger.warning(
                        'LDAP paged_search fallito (%s), fallback a ricerca semplice.',
                        type(paged_err).__name__
                    )
                    diag.paging_used = False
                    conn.search(
                        search_base=cfg.base_dn,
                        search_filter=diag.filter_used,
                        search_scope=ldap3.SUBTREE,
                        attributes=attrs,
                        size_limit=min(max_entries, 5000),
                    )
                    result_code = conn.result.get('result', -1)
                    diag.server_result_code = result_code
                    diag.server_result_description = conn.result.get('description', '')
                    if result_code == 4:  # LDAP_SIZELIMIT_EXCEEDED
                        diag.size_limit_exceeded = True
                        logger.warning(
                            'LDAP SIZELIMIT_EXCEEDED: solo le prime entry restituite. '
                            'Abilitare paging sul server.'
                        )
                    if result_code == 3:  # LDAP_TIMELIMIT_EXCEEDED
                        diag.time_limit_exceeded = True
                    for ldap_entry in conn.entries:
                        raw_total += 1
                        parsed = self._parse_entry_obj(
                            ldap_entry, attr_given, attr_sn, attr_account
                        )
                        if parsed:
                            entries.append(parsed)
                        else:
                            dropped += 1
                    pages_count = 1

        except Exception as e:
            diag.error = f'{type(e).__name__}: {str(e)[:120]}'
            logger.warning('Errore connessione LDAP (%s)', type(e).__name__)
            diag.elapsed_ms = int((time.monotonic() - t0) * 1000)
            raise

        diag.pages_count = pages_count
        diag.raw_entries_count_total = raw_total
        diag.parsed_users_count_total = len(entries)
        diag.dropped_missing_attrs_count = dropped
        diag.elapsed_ms = int((time.monotonic() - t0) * 1000)

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

        logger.info(
            'LDAP cache: %d utenti, %d pagine, %d raw, %d dropped, %dms (sanitizzato)',
            len(entries), pages_count, raw_total, dropped, diag.elapsed_ms
        )
        return diag

    def _parse_attrs(self, attrs_dict: dict, dn: str,
                     attr_given: str, attr_sn: str, attr_account: str) -> Optional[LdapEntry]:
        """Parsa dict attributi da paged_search generator."""
        def _get(key: str) -> str:
            val = attrs_dict.get(key) or attrs_dict.get(key.lower()) or ''
            if isinstance(val, list):
                val = val[0] if val else ''
            return str(val).strip()

        given = _get(attr_given) or _get('givenName')
        sn = _get(attr_sn) or _get('sn')
        # Fallback chain per account
        cn = (_get(attr_account) or _get('cn') or _get('uid')
              or _get('sAMAccountName') or _parse_cn_from_dn(dn))
        if not (given or sn or cn):
            return None
        full = canonicalize_person_name(f'{given} {sn}') if given and sn else ''
        full_rev = canonicalize_person_name(f'{sn} {given}') if given and sn else ''
        return LdapEntry(
            given_name=canonicalize_person_name(given),
            surname=canonicalize_person_name(sn),
            cn=canonicalize_account(cn),
            full_name=full,
            full_name_rev=full_rev,
        )

    def _parse_entry_obj(self, entry, attr_given: str, attr_sn: str,
                         attr_account: str) -> Optional[LdapEntry]:
        """Parsa oggetto entry ldap3 (da conn.entries)."""
        def _get(attr: str) -> str:
            val = getattr(entry, attr, None)
            if val is None:
                return ''
            s = str(val).strip()
            return '' if s in ('[]', 'None', '') else s

        given = _get(attr_given) or _get('givenName')
        sn = _get(attr_sn) or _get('sn')
        cn = (_get(attr_account) or _get('cn') or _get('uid')
              or _get('sAMAccountName') or _parse_cn_from_dn(str(entry.entry_dn or '')))
        if not (given or sn or cn):
            return None
        full = canonicalize_person_name(f'{given} {sn}') if given and sn else ''
        full_rev = canonicalize_person_name(f'{sn} {given}') if given and sn else ''
        return LdapEntry(
            given_name=canonicalize_person_name(given),
            surname=canonicalize_person_name(sn),
            cn=canonicalize_account(cn),
            full_name=full,
            full_name_rev=full_rev,
        )

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
            return True, f'Cache aggiornata: {diag.parsed_users_count_total} utenti', diag.to_dict()
        except Exception as e:
            diag = self._last_diagnostics
            return False, f'{type(e).__name__}: {str(e)[:100]}', diag.to_dict() if diag else None

    def test_connection(self) -> Tuple[bool, str, Optional[int], Optional[dict]]:
        """Testa connessione LDAP. Restituisce (success, message, count, diagnostics)."""
        if not self._config or not self._config.enabled:
            return False, 'LDAP non configurato o disabilitato', None, None
        try:
            diag = self._do_refresh()
            return True, 'Connessione riuscita', diag.parsed_users_count_total, diag.to_dict()
        except Exception as e:
            diag = self._last_diagnostics
            return False, f'{type(e).__name__}: {str(e)[:100]}', None, diag.to_dict() if diag else None

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
_TOKEN_RE = re.compile(r'[A-Za-z0-9_.\-\u00C0-\u024F]+', re.UNICODE)


def _tokenize_with_spans(text: str):
    """Restituisce lista di (token_lower, start, end)."""
    return [
        (m.group(0).casefold(), m.start(), m.end())
        for m in _TOKEN_RE.finditer(text)
    ]


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
        return 'LdapPersonDetector'

    def _is_enabled(self) -> bool:
        cfg = self._config or _ldap_config
        return cfg is not None and cfg.enabled

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula or not self._is_enabled():
            return []

        accounts_set, fullname_set, fullname_reverse_map, account_to_canonical = (
            _ldap_cache.get_lookup_sets()
        )
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
                findings.append(RawFinding(
                    entity_type=EntityType.ACCOUNT,
                    original_value=original,
                    canonical_value=canonical,
                    source_chunk=chunk,
                    confidence_score=0.92,
                    detector_name=self.name,
                    start_pos=start,
                    end_pos=end,
                ))

        # ── Fullname matching (bigramma) ──────────────────────
        for i in range(len(tokens) - 1):
            tok1_lower, start1, _ = tokens[i]
            tok2_lower, _, end2 = tokens[i + 1]
            bigram = f'{tok1_lower} {tok2_lower}'

            canonical_fn = None
            if bigram in fullname_set:
                canonical_fn = bigram
            elif bigram in fullname_reverse_map:
                canonical_fn = fullname_reverse_map[bigram]

            if canonical_fn:
                original = text[start1:end2]
                findings.append(RawFinding(
                    entity_type=EntityType.LDAP_PERSON,
                    original_value=original,
                    canonical_value=canonical_fn,
                    source_chunk=chunk,
                    confidence_score=0.95,
                    detector_name=self.name,
                    start_pos=start1,
                    end_pos=end2,
                ))

        return findings
