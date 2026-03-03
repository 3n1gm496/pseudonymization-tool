"""
Test di copertura per app/detectors/ldap_client.py e app/detectors/ldap_detector.py.
Usa mock per evitare connessioni LDAP reali.
Copre: utility functions, LdapDiagnostics.to_dict, LdapEntry.all_tokens,
LdapClient._parse_attrs, LdapClient._parse_entry_obj, LdapClient.query_users
(ldap3 non installato, config disabilitata), LdapCache (configure, get_lookup_sets,
get_diagnostics, refresh_now, test_connection, stop), LdapPersonDetector.detect,
configure_ldap, get_ldap_cache, get_ldap_config.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.detectors.ldap_client import (
    LdapClient,
    LdapDiagnostics,
    LdapEntry,
    _nfkc,
    _parse_cn_from_dn,
    canonicalize_account,
    canonicalize_person_name,
)
from app.detectors.ldap_detector import (
    LdapCache,
    LdapPersonDetector,
    configure_ldap,
    get_ldap_cache,
    get_ldap_config,
)
from app.models.schemas import LdapConfig
from app.parsers.base import TextChunk


# ─── Utility functions ────────────────────────────────────────────────────────

def test_nfkc_empty():
    assert _nfkc("") == ""


def test_nfkc_normalizes():
    result = _nfkc("  Alice  ")
    assert result == "alice"


def test_canonicalize_account():
    assert canonicalize_account("ALICE.SMITH") == "alice.smith"


def test_canonicalize_person_name():
    assert canonicalize_person_name("  Alice   Smith  ") == "alice smith"


def test_parse_cn_from_dn_empty():
    assert _parse_cn_from_dn("") == ""


def test_parse_cn_from_dn_valid():
    assert _parse_cn_from_dn("CN=Alice Smith,OU=Users,DC=example,DC=com") == "Alice Smith"


def test_parse_cn_from_dn_no_cn():
    assert _parse_cn_from_dn("OU=Users,DC=example,DC=com") == ""


# ─── LdapDiagnostics ──────────────────────────────────────────────────────────

def test_ldap_diagnostics_to_dict():
    diag = LdapDiagnostics(
        scope_used="SUBTREE",
        filter_used="(objectClass=person)",
        base_dn_used="DC=example,DC=com",
        paging_used=True,
        page_size=100,
        pages_count=2,
        raw_entries_count_total=150,
        parsed_users_count_total=148,
        dropped_missing_attrs_count=2,
        last_cookie_present=False,
        server_result_code=0,
        server_result_description="success",
        elapsed_ms=42,
        error=None,
    )
    d = diag.to_dict()
    assert d["scope_used"] == "SUBTREE"
    assert d["pages_count"] == 2
    assert d["parsed_users_count_total"] == 148
    assert d["error"] is None


# ─── LdapEntry ────────────────────────────────────────────────────────────────

def test_ldap_entry_fields():
    entry = LdapEntry(
        given_name="alice",
        surname="smith",
        cn="asmith",
        full_name="alice smith",
        full_name_rev="smith alice",
    )
    assert entry.given_name == "alice"
    assert entry.surname == "smith"
    assert entry.cn == "asmith"
    assert entry.full_name == "alice smith"
    assert entry.full_name_rev == "smith alice"


def test_ldap_entry_empty_fields():
    entry = LdapEntry(given_name="", surname="", cn="", full_name="", full_name_rev="")
    assert entry.given_name == ""
    assert entry.cn == ""


# ─── LdapClient._parse_attrs ──────────────────────────────────────────────────

def _make_ldap_config(enabled=True):
    return LdapConfig(
        enabled=enabled,
        host="ldap.example.com",
        port=389,
        use_ssl=False,
        bind_dn="cn=admin,dc=example,dc=com",
        bind_password="secret",
        base_dn="dc=example,dc=com",
        user_filter="(objectClass=person)",
        attr_given_name="givenName",
        attr_surname="sn",
        attr_account="sAMAccountName",
        page_size=100,
        max_entries=1000,
        refresh_interval_minutes=60,
    )


def test_parse_attrs_full_entry():
    config = _make_ldap_config()
    client = LdapClient(config)
    attrs = {
        "givenName": "Alice",
        "sn": "Smith",
        "sAMAccountName": "asmith",
    }
    entry = client._parse_attrs(attrs, "CN=Alice Smith,DC=example,DC=com", "givenName", "sn", "sAMAccountName")
    assert entry is not None
    assert entry.given_name == "alice"
    assert entry.surname == "smith"
    assert entry.cn == "asmith"
    assert entry.full_name == "alice smith"


def test_parse_attrs_list_values():
    config = _make_ldap_config()
    client = LdapClient(config)
    attrs = {
        "givenName": ["Alice"],
        "sn": ["Smith"],
        "sAMAccountName": ["asmith"],
    }
    entry = client._parse_attrs(attrs, "CN=Alice,DC=example,DC=com", "givenName", "sn", "sAMAccountName")
    assert entry is not None
    assert entry.given_name == "alice"


def test_parse_attrs_missing_all_returns_none():
    config = _make_ldap_config()
    client = LdapClient(config)
    entry = client._parse_attrs({}, "", "givenName", "sn", "sAMAccountName")
    assert entry is None


def test_parse_attrs_cn_fallback_from_dn():
    config = _make_ldap_config()
    client = LdapClient(config)
    attrs = {"givenName": "Bob"}
    entry = client._parse_attrs(attrs, "CN=BobAccount,DC=example,DC=com", "givenName", "sn", "sAMAccountName")
    assert entry is not None
    assert entry.cn == "bobaccount"


# ─── LdapClient._parse_entry_obj ──────────────────────────────────────────────

def test_parse_entry_obj_full():
    config = _make_ldap_config()
    client = LdapClient(config)
    mock_entry = SimpleNamespace(
        givenName="Alice",
        sn="Smith",
        sAMAccountName="asmith",
        entry_dn="CN=Alice Smith,DC=example,DC=com",
    )
    entry = client._parse_entry_obj(mock_entry, "givenName", "sn", "sAMAccountName")
    assert entry is not None
    assert entry.given_name == "alice"
    assert entry.cn == "asmith"


def test_parse_entry_obj_none_attrs():
    config = _make_ldap_config()
    client = LdapClient(config)
    mock_entry = SimpleNamespace(
        givenName=None,
        sn=None,
        sAMAccountName=None,
        entry_dn=None,
    )
    entry = client._parse_entry_obj(mock_entry, "givenName", "sn", "sAMAccountName")
    assert entry is None


def test_parse_entry_obj_bracket_values_ignored():
    """Testa che valori '[]' e 'None' vengano trattati come vuoti."""
    config = _make_ldap_config()
    client = LdapClient(config)
    mock_entry = SimpleNamespace(
        givenName="[]",
        sn="None",
        sAMAccountName="asmith",
        entry_dn="CN=asmith,DC=example,DC=com",
    )
    entry = client._parse_entry_obj(mock_entry, "givenName", "sn", "sAMAccountName")
    assert entry is not None
    assert entry.given_name == ""
    assert entry.surname == ""
    assert entry.cn == "asmith"


# ─── LdapClient.query_users — config disabilitata ─────────────────────────────

def test_query_users_disabled_config():
    config = _make_ldap_config(enabled=False)
    client = LdapClient(config)
    entries, diag = client.query_users()
    assert entries == []
    assert diag.error is None


def test_query_users_ldap3_not_installed():
    """Testa il caso in cui ldap3 non è installato."""
    config = _make_ldap_config(enabled=True)
    client = LdapClient(config)
    with patch.dict("sys.modules", {"ldap3": None}):
        entries, diag = client.query_users()
    assert entries == []
    assert diag.error is not None


# ─── LdapCache ────────────────────────────────────────────────────────────────

def test_ldap_cache_get_lookup_sets_empty():
    cache = LdapCache()
    accounts, fullnames, reverse_map, account_to_canonical = cache.get_lookup_sets()
    assert accounts == set()
    assert fullnames == set()
    assert reverse_map == {}
    assert account_to_canonical == {}


def test_ldap_cache_get_diagnostics_none():
    cache = LdapCache()
    assert cache.get_diagnostics() is None


def test_ldap_cache_refresh_now_no_config():
    cache = LdapCache()
    success, msg, diag = cache.refresh_now()
    assert success is True
    assert "0 utenti" in msg


def test_ldap_cache_test_connection_not_configured():
    cache = LdapCache()
    success, msg, count, diag = cache.test_connection()
    assert success is False
    assert "non configurato" in msg
    assert count is None


def test_ldap_cache_stop():
    cache = LdapCache()
    cache.stop()
    assert cache._stop_event.is_set()


def test_ldap_cache_do_refresh_with_mock_client():
    """Testa _do_refresh con LdapClient mockato che restituisce entries."""
    from app.detectors.ldap_client import LdapEntry

    config = _make_ldap_config(enabled=True)
    cache = LdapCache()
    cache._config = config

    mock_entries = [
        LdapEntry(given_name="alice", surname="smith", cn="asmith", full_name="alice smith", full_name_rev="smith alice"),
        LdapEntry(given_name="bob", surname="jones", cn="bjones", full_name="bob jones", full_name_rev="jones bob"),
    ]
    mock_diag = LdapDiagnostics(parsed_users_count_total=2, pages_count=1, elapsed_ms=10)

    with patch("app.detectors.ldap_detector.LdapClient") as MockClient:
        MockClient.return_value.query_users.return_value = (mock_entries, mock_diag)
        diag = cache._do_refresh()

    assert diag.parsed_users_count_total == 2
    accounts, fullnames, reverse_map, account_to_canonical = cache.get_lookup_sets()
    assert "asmith" in accounts
    assert "bjones" in accounts
    assert "alice smith" in fullnames
    assert "bob jones" in fullnames
    assert reverse_map["smith alice"] == "alice smith"


def test_ldap_cache_get_diagnostics_after_refresh():
    config = _make_ldap_config(enabled=True)
    cache = LdapCache()
    cache._config = config

    mock_diag = LdapDiagnostics(parsed_users_count_total=5, elapsed_ms=20)
    with patch("app.detectors.ldap_detector.LdapClient") as MockClient:
        MockClient.return_value.query_users.return_value = ([], mock_diag)
        cache._do_refresh()

    diag_dict = cache.get_diagnostics()
    assert diag_dict is not None
    assert diag_dict["parsed_users_count_total"] == 5


def test_ldap_cache_test_connection_success():
    config = _make_ldap_config(enabled=True)
    cache = LdapCache()
    cache._config = config

    mock_diag = LdapDiagnostics(parsed_users_count_total=3)
    with patch("app.detectors.ldap_detector.LdapClient") as MockClient:
        MockClient.return_value.query_users.return_value = ([], mock_diag)
        success, msg, count, diag = cache.test_connection()

    assert success is True
    assert count == 3


# ─── configure_ldap / get_ldap_cache / get_ldap_config ───────────────────────

def test_configure_ldap_and_getters():
    config = _make_ldap_config(enabled=False)
    configure_ldap(config)
    assert get_ldap_config() is config
    assert get_ldap_cache() is not None


# ─── LdapPersonDetector ───────────────────────────────────────────────────────

def _make_chunk(text: str) -> TextChunk:
    return TextChunk(text=text, source_ref="riga 1", line_number=1)


def test_ldap_person_detector_disabled():
    """Testa che il detector non rilevi nulla se LDAP è disabilitato."""
    config = _make_ldap_config(enabled=False)
    detector = LdapPersonDetector(config=config)
    chunk = _make_chunk("alice smith logged in")
    findings = detector.detect(chunk)
    assert findings == []


def test_ldap_person_detector_empty_cache():
    """Testa che con cache vuota non vengano prodotti finding."""
    config = _make_ldap_config(enabled=True)
    detector = LdapPersonDetector(config=config)
    # Cache vuota (nessun utente caricato)
    with patch("app.detectors.ldap_detector._ldap_cache") as mock_cache:
        mock_cache.get_lookup_sets.return_value = (set(), set(), {}, {})
        chunk = _make_chunk("alice smith logged in")
        findings = detector.detect(chunk)
    assert findings == []


def test_ldap_person_detector_account_match():
    """Testa il rilevamento di un account LDAP nel testo."""
    config = _make_ldap_config(enabled=True)
    detector = LdapPersonDetector(config=config)

    accounts_set = {"asmith"}
    fullname_set = {"alice smith"}
    reverse_map = {"smith alice": "alice smith"}
    account_to_canonical = {"asmith": "alice smith"}

    with patch("app.detectors.ldap_detector._ldap_cache") as mock_cache:
        mock_cache.get_lookup_sets.return_value = (accounts_set, fullname_set, reverse_map, account_to_canonical)
        chunk = _make_chunk("User asmith logged in at 10:00")
        findings = detector.detect(chunk)

    account_findings = [f for f in findings if f.entity_type.value == "ACCOUNT"]
    assert len(account_findings) >= 1
    assert account_findings[0].original_value == "asmith"
    assert account_findings[0].canonical_value == "alice smith"


def test_ldap_person_detector_fullname_match():
    """Testa il rilevamento di un fullname LDAP (bigramma) nel testo."""
    config = _make_ldap_config(enabled=True)
    detector = LdapPersonDetector(config=config)

    accounts_set = set()
    fullname_set = {"alice smith"}
    reverse_map = {"smith alice": "alice smith"}
    account_to_canonical = {}

    with patch("app.detectors.ldap_detector._ldap_cache") as mock_cache:
        mock_cache.get_lookup_sets.return_value = (accounts_set, fullname_set, reverse_map, account_to_canonical)
        chunk = _make_chunk("Document created by alice smith today")
        findings = detector.detect(chunk)

    ldap_findings = [f for f in findings if f.entity_type.value == "LDAP_PERSON"]
    assert len(ldap_findings) >= 1
    assert "alice smith" in ldap_findings[0].original_value.lower()


def test_ldap_person_detector_reverse_fullname_match():
    """Testa il rilevamento di un fullname invertito (cognome nome)."""
    config = _make_ldap_config(enabled=True)
    detector = LdapPersonDetector(config=config)

    accounts_set = set()
    fullname_set = {"alice smith"}
    reverse_map = {"smith alice": "alice smith"}
    account_to_canonical = {}

    with patch("app.detectors.ldap_detector._ldap_cache") as mock_cache:
        mock_cache.get_lookup_sets.return_value = (accounts_set, fullname_set, reverse_map, account_to_canonical)
        chunk = _make_chunk("Report by smith alice")
        findings = detector.detect(chunk)

    ldap_findings = [f for f in findings if f.entity_type.value == "LDAP_PERSON"]
    assert len(ldap_findings) >= 1
    assert ldap_findings[0].canonical_value == "alice smith"


def test_ldap_person_detector_formula_chunk_skipped():
    """Testa che i chunk formula vengano saltati."""
    config = _make_ldap_config(enabled=True)
    detector = LdapPersonDetector(config=config)
    chunk = TextChunk(text="=VLOOKUP(asmith, A1:B10, 2)", source_ref="cella A1", line_number=1, is_formula=True)
    with patch("app.detectors.ldap_detector._ldap_cache") as mock_cache:
        mock_cache.get_lookup_sets.return_value = ({"asmith"}, set(), {}, {})
        findings = detector.detect(chunk)
    assert findings == []
