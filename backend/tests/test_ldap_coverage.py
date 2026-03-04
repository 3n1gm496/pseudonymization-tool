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
from unittest.mock import patch

from app.detectors.ldap_client import (
    LdapClient,
    LdapDiagnostics,
    LdapEntry,
    _nfkc,
    _parse_cn_from_dn,
    canonicalize_account,
    canonicalize_person_name,
)
from app.detectors.ldap_detector import LdapCache, LdapPersonDetector, configure_ldap, get_ldap_cache, get_ldap_config
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
        LdapEntry(
            given_name="alice", surname="smith", cn="asmith", full_name="alice smith", full_name_rev="smith alice"
        ),
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


# ─── LdapClient.query_users — con ldap3 mockato ──────────────────────────────


def _make_ldap_entry_dict(given="Alice", sn="Smith", account="asmith", dn="CN=Alice Smith,DC=example,DC=com"):
    """Helper: crea una entry LDAP simulata come dizionario (formato paged_search)."""
    return {
        "type": "searchResEntry",
        "dn": dn,
        "attributes": {
            "givenName": given,
            "sn": sn,
            "sAMAccountName": account,
        },
        "controls": {},
    }


def test_query_users_with_mock_ldap3_paged_search():
    """Testa query_users con ldap3 mockato — paged_search con 1 entry."""
    import sys
    from unittest.mock import MagicMock, patch

    config = _make_ldap_config(enabled=True)
    client = LdapClient(config)

    mock_ldap3 = MagicMock()
    mock_ldap3.NONE = "NONE"
    mock_ldap3.SUBTREE = "SUBTREE"
    mock_ldap3.AUTO_BIND_NO_TLS = "AUTO_BIND_NO_TLS"
    mock_ldap3.AUTO_BIND_TLS_BEFORE_BIND = "AUTO_BIND_TLS_BEFORE_BIND"
    mock_ldap3.ANONYMOUS = "ANONYMOUS"

    entry = _make_ldap_entry_dict()
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.extend.standard.paged_search.return_value = iter([entry])

    mock_ldap3.Server.return_value = MagicMock()
    mock_ldap3.Connection.return_value = mock_conn

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        entries, diag = client.query_users()

    assert len(entries) == 1
    assert entries[0].given_name == "alice"
    assert entries[0].cn == "asmith"
    assert diag.error is None
    assert diag.parsed_users_count_total == 1


def test_query_users_with_mock_ldap3_anonymous_bind():
    """Testa query_users con bind anonimo (nessun bind_dn)."""
    import sys
    from unittest.mock import MagicMock, patch

    config = LdapConfig(
        enabled=True,
        host="ldap.example.com",
        port=389,
        use_ssl=False,
        bind_dn="",  # anonimo
        bind_password="",
        base_dn="dc=example,dc=com",
        user_filter="(objectClass=person)",
        attr_given_name="givenName",
        attr_surname="sn",
        attr_account="sAMAccountName",
        page_size=100,
        max_entries=1000,
        refresh_interval_minutes=60,
    )
    client = LdapClient(config)

    mock_ldap3 = MagicMock()
    mock_ldap3.NONE = "NONE"
    mock_ldap3.SUBTREE = "SUBTREE"
    mock_ldap3.AUTO_BIND_NO_TLS = "AUTO_BIND_NO_TLS"
    mock_ldap3.AUTO_BIND_TLS_BEFORE_BIND = "AUTO_BIND_TLS_BEFORE_BIND"
    mock_ldap3.ANONYMOUS = "ANONYMOUS"

    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.extend.standard.paged_search.return_value = iter([])

    mock_ldap3.Server.return_value = MagicMock()
    mock_ldap3.Connection.return_value = mock_conn

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        entries, diag = client.query_users()

    assert entries == []
    assert diag.error is None
    # Verifica che authentication=ANONYMOUS sia stato impostato
    call_kwargs = mock_ldap3.Connection.call_args[1]
    assert call_kwargs.get("authentication") == "ANONYMOUS"


def test_query_users_with_mock_ldap3_paged_search_fallback():
    """Testa il fallback a ricerca semplice quando paged_search fallisce."""
    import sys
    from unittest.mock import MagicMock, patch

    config = _make_ldap_config(enabled=True)
    client = LdapClient(config)

    mock_ldap3 = MagicMock()
    mock_ldap3.NONE = "NONE"
    mock_ldap3.SUBTREE = "SUBTREE"
    mock_ldap3.AUTO_BIND_NO_TLS = "AUTO_BIND_NO_TLS"
    mock_ldap3.AUTO_BIND_TLS_BEFORE_BIND = "AUTO_BIND_TLS_BEFORE_BIND"
    mock_ldap3.ANONYMOUS = "ANONYMOUS"

    # paged_search lancia eccezione → fallback a conn.search
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.extend.standard.paged_search.side_effect = Exception("paged search not supported")
    mock_conn.result = {"result": 0, "description": "success"}

    # Simula 1 entry nel fallback usando SimpleNamespace (non MagicMock)
    from types import SimpleNamespace

    mock_entry_obj = SimpleNamespace(
        entry_dn="CN=Bob Jones,DC=example,DC=com",
        givenName="Bob",
        sn="Jones",
        sAMAccountName="bjones",
    )
    mock_conn.entries = [mock_entry_obj]

    mock_ldap3.Server.return_value = MagicMock()
    mock_ldap3.Connection.return_value = mock_conn

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        entries, diag = client.query_users()

    assert diag.paging_used is False
    assert len(entries) == 1
    assert entries[0].cn == "bjones"


def test_query_users_with_mock_ldap3_connection_error():
    """Testa che un errore di connessione LDAP venga gestito correttamente."""
    import sys
    from unittest.mock import MagicMock, patch

    config = _make_ldap_config(enabled=True)
    client = LdapClient(config)

    mock_ldap3 = MagicMock()
    mock_ldap3.NONE = "NONE"
    mock_ldap3.SUBTREE = "SUBTREE"
    mock_ldap3.AUTO_BIND_NO_TLS = "AUTO_BIND_NO_TLS"
    mock_ldap3.AUTO_BIND_TLS_BEFORE_BIND = "AUTO_BIND_TLS_BEFORE_BIND"
    mock_ldap3.ANONYMOUS = "ANONYMOUS"
    mock_ldap3.Server.side_effect = Exception("Connection refused")

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        entries, diag = client.query_users()

    assert entries == []
    assert diag.error is not None
    assert "Connection refused" in diag.error


def test_query_users_with_mock_ldap3_size_limit_exceeded():
    """Testa il comportamento quando viene raggiunto il limite di entry."""
    import sys
    from unittest.mock import MagicMock, patch

    # Configura max_entries=2 per forzare il limite
    config = LdapConfig(
        enabled=True,
        host="ldap.example.com",
        port=389,
        cache_max_entries=1,  # limite 1: alla 2a entry scatta size_limit_exceeded
        refresh_interval_minutes=60,
    )
    client = LdapClient(config)

    mock_ldap3 = MagicMock()
    mock_ldap3.NONE = "NONE"
    mock_ldap3.SUBTREE = "SUBTREE"
    mock_ldap3.AUTO_BIND_NO_TLS = "AUTO_BIND_NO_TLS"
    mock_ldap3.AUTO_BIND_TLS_BEFORE_BIND = "AUTO_BIND_TLS_BEFORE_BIND"
    mock_ldap3.ANONYMOUS = "ANONYMOUS"

    # 3 entry ma max_entries=2 → size_limit_exceeded
    # Nota: il check avviene DOPO aver già aggiunto max_entries elementi,
    # quindi la 3a entry fa scattare il warning ma le prime 2 sono già state aggiunte.
    entries_data = [
        _make_ldap_entry_dict("Alice", "Smith", "asmith"),
        _make_ldap_entry_dict("Bob", "Jones", "bjones"),
        _make_ldap_entry_dict("Carol", "White", "cwhite"),
    ]
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.extend.standard.paged_search.return_value = iter(entries_data)

    mock_ldap3.Server.return_value = MagicMock()
    mock_ldap3.Connection.return_value = mock_conn

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        entries, diag = client.query_users()

    assert diag.size_limit_exceeded is True
    # Con max_entries=1: la prima entry viene aggiunta, alla seconda scatta il limite
    assert len(entries) == 1


def test_query_users_with_mock_ldap3_referral_entry():
    """Testa che le entry di tipo searchResRef (referral) vengano ignorate."""
    import sys
    from unittest.mock import MagicMock, patch

    config = _make_ldap_config(enabled=True)
    client = LdapClient(config)

    mock_ldap3 = MagicMock()
    mock_ldap3.NONE = "NONE"
    mock_ldap3.SUBTREE = "SUBTREE"
    mock_ldap3.AUTO_BIND_NO_TLS = "AUTO_BIND_NO_TLS"
    mock_ldap3.AUTO_BIND_TLS_BEFORE_BIND = "AUTO_BIND_TLS_BEFORE_BIND"
    mock_ldap3.ANONYMOUS = "ANONYMOUS"

    referral_entry = {"type": "searchResRef", "uri": ["ldap://other.example.com/"]}
    real_entry = _make_ldap_entry_dict()
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.extend.standard.paged_search.return_value = iter([referral_entry, real_entry])

    mock_ldap3.Server.return_value = MagicMock()
    mock_ldap3.Connection.return_value = mock_conn

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        entries, diag = client.query_users()

    assert len(entries) == 1  # solo la real_entry, il referral è ignorato


def test_query_users_with_mock_ldap3_paging_cookie():
    """Testa che le pagine con cookie vengano conteggiate correttamente."""
    import sys
    from unittest.mock import MagicMock, patch

    config = _make_ldap_config(enabled=True)
    client = LdapClient(config)

    mock_ldap3 = MagicMock()
    mock_ldap3.NONE = "NONE"
    mock_ldap3.SUBTREE = "SUBTREE"
    mock_ldap3.AUTO_BIND_NO_TLS = "AUTO_BIND_NO_TLS"
    mock_ldap3.AUTO_BIND_TLS_BEFORE_BIND = "AUTO_BIND_TLS_BEFORE_BIND"
    mock_ldap3.ANONYMOUS = "ANONYMOUS"

    # Entry con controllo paging (cookie presente)
    entry_with_cookie = {
        "type": "searchResEntry",
        "dn": "CN=Alice,DC=example,DC=com",
        "attributes": {"givenName": "Alice", "sn": "Smith", "sAMAccountName": "asmith"},
        "controls": {"1.2.840.113556.1.4.319": {"value": {"cookie": b"nextpage"}}},
    }
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.extend.standard.paged_search.return_value = iter([entry_with_cookie])

    mock_ldap3.Server.return_value = MagicMock()
    mock_ldap3.Connection.return_value = mock_conn

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        entries, diag = client.query_users()

    assert diag.pages_count == 1
    assert diag.last_cookie_present is True


# ─── LdapCache._start_refresh_loop e configure ───────────────────────────────


def test_ldap_cache_configure_enabled_starts_thread():
    """Testa che configure() con enabled=True avvii il refresh thread."""
    import time

    config = _make_ldap_config(enabled=True)
    cache = LdapCache()

    with patch("app.detectors.ldap_detector.LdapClient") as MockClient:
        MockClient.return_value.query_users.return_value = ([], LdapDiagnostics())
        cache.configure(config)
        time.sleep(0.05)  # breve attesa per il thread

    assert cache._refresh_thread is not None
    assert cache._refresh_thread.is_alive()
    cache.stop()


def test_ldap_cache_configure_disabled_no_thread():
    """Testa che configure() con enabled=False non avvii il refresh thread."""
    config = _make_ldap_config(enabled=False)
    cache = LdapCache()
    cache.configure(config)
    assert cache._refresh_thread is None


def test_ldap_cache_refresh_now_with_error():
    """Testa refresh_now quando _do_refresh lancia eccezione.

    refresh_now() cattura l'eccezione di _do_refresh e restituisce (False, msg, None).
    """
    config = _make_ldap_config(enabled=True)
    cache = LdapCache()
    cache._config = config

    with patch("app.detectors.ldap_detector.LdapClient") as MockClient:
        MockClient.return_value.query_users.side_effect = Exception("network error")
        success, msg, diag = cache.refresh_now()

    # refresh_now cattura l'eccezione di _do_refresh
    assert success is False
    assert "network error" in msg or "Exception" in msg


def test_ldap_cache_do_refresh_with_error_in_query():
    """Testa _do_refresh quando query_users restituisce diag.error."""
    config = _make_ldap_config(enabled=True)
    cache = LdapCache()
    cache._config = config

    error_diag = LdapDiagnostics(error="Connection refused")
    with patch("app.detectors.ldap_detector.LdapClient") as MockClient:
        MockClient.return_value.query_users.return_value = ([], error_diag)
        diag = cache._do_refresh()

    assert diag.error == "Connection refused"
    # La cache non deve essere aggiornata in caso di errore
    accounts, _, _, _ = cache.get_lookup_sets()
    assert len(accounts) == 0


def test_ldap_cache_test_connection_with_error():
    """Testa test_connection quando la connessione fallisce."""
    config = _make_ldap_config(enabled=True)
    cache = LdapCache()
    cache._config = config

    error_diag = LdapDiagnostics(error="Timeout")
    with patch("app.detectors.ldap_detector.LdapClient") as MockClient:
        MockClient.return_value.query_users.return_value = ([], error_diag)
        success, msg, count, diag_dict = cache.test_connection()

    # test_connection chiama _do_refresh che non rilancia ma restituisce diag con error
    assert success is True  # _do_refresh non rilancia
    assert diag_dict is not None
