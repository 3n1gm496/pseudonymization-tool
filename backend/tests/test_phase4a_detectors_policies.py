
from app.core import policies
from app.detectors.dictionary_detector import DictionaryDetector
from app.detectors.regex_detectors import (
    EMAIL_DETECTOR,
    IPV4_DETECTOR,
    PARTITA_IVA_DETECTOR,
    _validate_codice_fiscale,
    _validate_ipv4,
    _validate_partita_iva,
)
from app.detectors.soc_detectors import (
    DeobfuscatedDetector,
    DomainFragmentDetector,
    LDAPDNDetector,
    LinuxPathDetector,
    MailHeadersDetector,
    UPNDetector,
    WindowsSIDDetector,
)
from app.models.schemas import EntityType, PresetName
from app.parsers.base import TextChunk


def _chunk(text: str, is_formula: bool = False) -> TextChunk:
    return TextChunk(text=text, source_ref="test", is_formula=is_formula)


def test_regex_email_normalization_lowercase():
    findings = EMAIL_DETECTOR.detect(_chunk("Contact: Mario.Rossi@Example.COM"))
    assert len(findings) == 1
    assert findings[0].original_value == "mario.rossi@example.com"
    assert findings[0].entity_type == EntityType.EMAIL


def test_regex_ipv4_validator_excludes_loopback_and_bad_octets():
    assert _validate_ipv4("192.168.10.20") is True
    assert _validate_ipv4("127.0.0.1") is False
    assert _validate_ipv4("999.1.1.1") is False
    assert _validate_ipv4("1.2.3") is False


def test_regex_ipv4_detector_skips_excluded():
    findings = IPV4_DETECTOR.detect(_chunk("IPs: 127.0.0.1 and 10.1.2.3"))
    assert len(findings) == 1
    assert findings[0].original_value == "10.1.2.3"


def test_regex_partita_iva_context_capture_group():
    findings = PARTITA_IVA_DETECTOR.detect(_chunk("Partita IVA: IT12345678901"))
    assert len(findings) == 1
    assert findings[0].original_value == "12345678901"
    assert findings[0].entity_type == EntityType.PARTITA_IVA


def test_regex_validators_for_cf_and_piva():
    assert _validate_codice_fiscale("RSSMRA85M01H501Z") is True
    assert _validate_codice_fiscale("RSSMRA85M01H501") is False

    assert _validate_partita_iva("01114601006") is True
    assert _validate_partita_iva("01114601007") is False


def test_regex_detector_skips_formula_chunks():
    findings = EMAIL_DETECTOR.detect(_chunk("john@example.com", is_formula=True))
    assert findings == []


def test_dictionary_detector_load_and_detect(tmp_path):
    (tmp_path / "person_names.txt").write_text("Mario Rossi\n# comment\n", encoding="utf-8")
    detector = DictionaryDetector(dictionaries_dir=tmp_path)

    findings = detector.detect(_chunk("Utente: mario rossi"))
    assert len(findings) == 1
    assert findings[0].entity_type == EntityType.PERSON
    assert findings[0].detector_name.startswith("DictionaryDetector")


def test_dictionary_detector_reload(tmp_path):
    dict_file = tmp_path / "project_codes.txt"
    dict_file.write_text("PRJ-ALPHA\n", encoding="utf-8")
    detector = DictionaryDetector(dictionaries_dir=tmp_path)
    assert detector.loaded_terms_count == 1

    dict_file.write_text("PRJ-ALPHA\nPRJ-BETA\n", encoding="utf-8")
    detector.reload()
    assert detector.loaded_terms_count == 2


def test_soc_upn_detector_detects_upn():
    findings = UPNDetector().detect(_chunk("Owner: mario.rossi@corp.local"))
    assert len(findings) == 1
    assert findings[0].entity_type == EntityType.UPN


def test_soc_ldap_dn_detector_detects_dn():
    findings = LDAPDNDetector().detect(_chunk("CN=Mario Rossi,OU=Users,DC=example,DC=com"))
    assert len(findings) == 1
    assert findings[0].entity_type == EntityType.LDAP_DN


def test_soc_windows_sid_detector_detects_sid():
    findings = WindowsSIDDetector().detect(_chunk("SID: S-1-5-21-3623811015-3361044348-30300820-1013"))
    assert len(findings) == 1
    assert findings[0].entity_type == EntityType.WINDOWS_SID


def test_soc_linux_path_detector_detects_abs_path():
    findings = LinuxPathDetector().detect(_chunk("Path: /var/log/auth.log"))
    assert len(findings) == 1
    assert findings[0].entity_type == EntityType.LINUX_PATH


def test_soc_mail_header_detector_extracts_email_from_header():
    text = "From: Mario Rossi <mario.rossi@example.com>\nSubject: test"
    findings = MailHeadersDetector().detect(_chunk(text))
    assert len(findings) == 1
    assert findings[0].entity_type == EntityType.MAIL_HEADER
    assert findings[0].original_value == "mario.rossi@example.com"


def test_soc_domain_fragment_detector_and_deobf_wrapper():
    inner = DomainFragmentDetector(["example", "corp.local"])
    direct = inner.detect(_chunk("domain example and corp.local"))
    assert len(direct) >= 2

    wrapped = DeobfuscatedDetector(inner)
    deobf_findings = wrapped.detect(_chunk("Visit example[.]com now"))
    assert len(deobf_findings) >= 1


def test_policies_defaults_and_hash_stability():
    soc_policy = policies.get_policy(PresetName.SOC_LOGS)
    assert "enabled_entity_types" in soc_policy
    assert policies.get_confidence_threshold(PresetName.SOC_LOGS) > 0

    h1 = policies.get_policy_hash(PresetName.SOC_LOGS)
    h2 = policies.get_policy_hash(PresetName.SOC_LOGS)
    assert h1 == h2
    assert len(h1) == 64


def test_policies_save_default_files(tmp_path):
    original_dir = policies.POLICIES_DIR
    try:
        policies.POLICIES_DIR = tmp_path
        policies.save_default_policies()

        expected = [
            "soc_logs.json",
            "policy_docs.json",
            "email_headers.json",
        ]
        for file_name in expected:
            assert (tmp_path / file_name).exists()
    finally:
        policies.POLICIES_DIR = original_dir
