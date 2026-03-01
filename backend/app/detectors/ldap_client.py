"""
LDAP Client — Connessione, querying, paging RFC2696.

Separato dal cache per:
- Testabilità (mockare il client)
- Riusabilità (client indipendente)
- Manutenibilità (separation of concerns)
"""

import logging
import time
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.models.schemas import LdapConfig

logger = logging.getLogger(__name__)


# ─── Utility Functions ────────────────────────────────────────────────────────


def _nfkc(s: str) -> str:
    """Unicode NFKC + strip + casefold."""
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s).strip().casefold()


def canonicalize_account(s: str) -> str:
    """Normalizza un account: NFKC + casefold + mantiene underscore/dot/hyphen."""
    return _nfkc(s)


def canonicalize_person_name(s: str) -> str:
    """Normalizza un nome: NFKC + casefold + collapse spaces."""
    n = _nfkc(s)
    return " ".join(n.split())


def _parse_cn_from_dn(dn: str) -> str:
    """Estrae il valore del primo RDN cn= da un DN LDAP."""
    if not dn:
        return ""
    for part in dn.split(","):
        part = part.strip()
        if part.lower().startswith("cn="):
            return part[3:].strip()
    return ""


@dataclass
class LdapDiagnostics:
    """Diagnostica dettagliata di una query LDAP."""

    scope_used: str = "SUBTREE"
    filter_used: str = ""
    base_dn_used: str = ""
    paging_used: bool = False
    page_size: int = 0
    pages_count: int = 0
    raw_entries_count_total: int = 0
    parsed_users_count_total: int = 0
    dropped_missing_attrs_count: int = 0
    last_cookie_present: bool = False
    server_result_code: Optional[int] = None
    server_result_description: str = ""
    size_limit_exceeded: bool = False
    time_limit_exceeded: bool = False
    elapsed_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "scope_used": self.scope_used,
            "filter_used": self.filter_used,
            "base_dn_used": self.base_dn_used,
            "paging_used": self.paging_used,
            "page_size": self.page_size,
            "pages_count": self.pages_count,
            "raw_entries_count_total": self.raw_entries_count_total,
            "parsed_users_count_total": self.parsed_users_count_total,
            "dropped_missing_attrs_count": self.dropped_missing_attrs_count,
            "last_cookie_present": self.last_cookie_present,
            "server_result_code": self.server_result_code,
            "server_result_description": self.server_result_description,
            "size_limit_exceeded": self.size_limit_exceeded,
            "time_limit_exceeded": self.time_limit_exceeded,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }


@dataclass
class LdapEntry:
    """Struttura normalizzata di un utente LDAP."""

    given_name: str  # givenName canonicalizzato
    surname: str  # sn canonicalizzato
    cn: str  # account canonicalizzato
    full_name: str  # "givenName sn" canonicalizzato
    full_name_rev: str  # "sn givenName" canonicalizzato


class LdapClient:
    """
    Client LDAP: connessione, paging RFC2696, parsing risultati.
    """

    def __init__(self, config: LdapConfig):
        self._config = config

    def query_users(self) -> Tuple[List[LdapEntry], LdapDiagnostics]:
        """
        Esegue query LDAP con paging RFC2696.
        Restituisce (entries_parsed, diagnostics).
        """
        diag = LdapDiagnostics()

        if not self._config or not self._config.enabled:
            return [], diag

        try:
            import ldap3
        except ImportError:
            logger.warning("ldap3 non installato. LDAP detection disabilitata.")
            diag.error = "ldap3 non installato"
            return [], diag

        cfg = self._config
        diag.base_dn_used = cfg.base_dn
        diag.filter_used = cfg.filter or (
            "(|(objectClass=inetOrgPerson)(objectClass=person)" "(objectClass=organizationalPerson)(objectClass=user))"
        )
        diag.scope_used = "SUBTREE"
        diag.paging_used = True
        page_size = min(getattr(cfg, "page_size", 500), 1000)
        diag.page_size = page_size
        max_entries = getattr(cfg, "cache_max_entries", 100000)

        # Attributi configurabili con fallback chain
        attr_given = getattr(cfg, "attr_given", "givenName") or "givenName"
        attr_sn = getattr(cfg, "attr_sn", "sn") or "sn"
        attr_account = getattr(cfg, "attr_account", "cn") or "cn"
        attrs = list({attr_given, attr_sn, attr_account, "cn", "uid", "sAMAccountName", "displayName"})

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
                connect_timeout=getattr(cfg, "connect_timeout", 10),
            )
            auto_bind = ldap3.AUTO_BIND_TLS_BEFORE_BIND if cfg.starttls else ldap3.AUTO_BIND_NO_TLS
            conn_kwargs = {
                "server": server,
                "auto_bind": auto_bind,
                "receive_timeout": getattr(cfg, "receive_timeout", 60),
            }
            if cfg.bind_dn:
                conn_kwargs["user"] = cfg.bind_dn
                conn_kwargs["password"] = cfg.bind_password
            else:
                conn_kwargs["authentication"] = ldap3.ANONYMOUS

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
                        if ldap_entry.get("type") == "searchResEntry":
                            raw_total += 1
                            if len(entries) >= max_entries:
                                logger.warning(
                                    "LDAP: raggiunto limite cache (%d). " "Aumentare cache_max_entries.", max_entries
                                )
                                diag.size_limit_exceeded = True
                                break
                            parsed = self._parse_attrs(
                                ldap_entry.get("attributes", {}),
                                ldap_entry.get("dn", ""),
                                attr_given,
                                attr_sn,
                                attr_account,
                            )
                            if parsed:
                                entries.append(parsed)
                            else:
                                dropped += 1
                        elif ldap_entry.get("type") == "searchResRef":
                            pass  # referral, ignorato
                        # Conta le pagine dai controlli
                        controls = ldap_entry.get("controls", {})
                        if "1.2.840.113556.1.4.319" in controls:
                            pages_count += 1
                            cookie = controls["1.2.840.113556.1.4.319"].get("value", {}).get("cookie", b"")
                            last_cookie = bool(cookie)

                    diag.last_cookie_present = last_cookie
                    if pages_count == 0:
                        pages_count = 1  # almeno una pagina

                except Exception as paged_err:
                    # Fallback: ricerca semplice senza paging
                    logger.warning(
                        "LDAP paged_search fallito (%s), fallback a ricerca semplice.", type(paged_err).__name__
                    )
                    diag.paging_used = False
                    conn.search(
                        search_base=cfg.base_dn,
                        search_filter=diag.filter_used,
                        search_scope=ldap3.SUBTREE,
                        attributes=attrs,
                        size_limit=min(max_entries, 5000),
                    )
                    result_code = conn.result.get("result", -1)
                    diag.server_result_code = result_code
                    diag.server_result_description = conn.result.get("description", "")
                    if result_code == 4:  # LDAP_SIZELIMIT_EXCEEDED
                        diag.size_limit_exceeded = True
                        logger.warning(
                            "LDAP SIZELIMIT_EXCEEDED: solo le prime entry restituite. " "Abilitare paging sul server."
                        )
                    if result_code == 3:  # LDAP_TIMELIMIT_EXCEEDED
                        diag.time_limit_exceeded = True
                    for ldap_entry in conn.entries:
                        raw_total += 1
                        parsed = self._parse_entry_obj(ldap_entry, attr_given, attr_sn, attr_account)
                        if parsed:
                            entries.append(parsed)
                        else:
                            dropped += 1
                    pages_count = 1

        except Exception as e:
            diag.error = f"{type(e).__name__}: {str(e)[:120]}"
            logger.warning("Errore connessione LDAP (%s)", type(e).__name__)
            diag.elapsed_ms = int((time.monotonic() - t0) * 1000)
            return [], diag

        diag.pages_count = pages_count
        diag.raw_entries_count_total = raw_total
        diag.parsed_users_count_total = len(entries)
        diag.dropped_missing_attrs_count = dropped
        diag.elapsed_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            "LDAP query: %d utenti, %d pagine, %d raw, %d dropped, %dms",
            len(entries),
            pages_count,
            raw_total,
            dropped,
            diag.elapsed_ms,
        )
        return entries, diag

    def _parse_attrs(
        self, attrs_dict: dict, dn: str, attr_given: str, attr_sn: str, attr_account: str
    ) -> Optional[LdapEntry]:
        """Parsa dict attributi da paged_search generator."""

        def _get(key: str) -> str:
            val = attrs_dict.get(key) or attrs_dict.get(key.lower()) or ""
            if isinstance(val, list):
                val = val[0] if val else ""
            return str(val).strip()

        given = _get(attr_given) or _get("givenName")
        sn = _get(attr_sn) or _get("sn")
        # Fallback chain per account
        cn = _get(attr_account) or _get("cn") or _get("uid") or _get("sAMAccountName") or _parse_cn_from_dn(dn)
        if not (given or sn or cn):
            return None
        full = canonicalize_person_name(f"{given} {sn}") if given and sn else ""
        full_rev = canonicalize_person_name(f"{sn} {given}") if given and sn else ""
        return LdapEntry(
            given_name=canonicalize_person_name(given),
            surname=canonicalize_person_name(sn),
            cn=canonicalize_account(cn),
            full_name=full,
            full_name_rev=full_rev,
        )

    def _parse_entry_obj(self, entry, attr_given: str, attr_sn: str, attr_account: str) -> Optional[LdapEntry]:
        """Parsa oggetto entry ldap3 (da conn.entries)."""

        def _get(attr: str) -> str:
            val = getattr(entry, attr, None)
            if val is None:
                return ""
            s = str(val).strip()
            return "" if s in ("[]", "None", "") else s

        given = _get(attr_given) or _get("givenName")
        sn = _get(attr_sn) or _get("sn")
        cn = (
            _get(attr_account)
            or _get("cn")
            or _get("uid")
            or _get("sAMAccountName")
            or _parse_cn_from_dn(str(entry.entry_dn or ""))
        )
        if not (given or sn or cn):
            return None
        full = canonicalize_person_name(f"{given} {sn}") if given and sn else ""
        full_rev = canonicalize_person_name(f"{sn} {given}") if given and sn else ""
        return LdapEntry(
            given_name=canonicalize_person_name(given),
            surname=canonicalize_person_name(sn),
            cn=canonicalize_account(cn),
            full_name=full,
            full_name_rev=full_rev,
        )
