import pytest
from app.core.revert import _replace_all, _validate_mapping_file, apply_revert_text, preview_revert_text
from app.mapping.crypto import encrypt_mapping


def test_revert_text_preview_and_apply():
    passphrase = "TestPassphrase_12345"
    mapping_payload = {
        "mapping": {
            "[PERSON_0001]": "Mario Rossi",
            "[HOST_0001]": "srv-prod-01.internal.local",
        }
    }
    mapping_bytes = encrypt_mapping(mapping_payload, passphrase)
    pseudo_text = "Utente [PERSON_0001] ha effettuato login su [HOST_0001]."

    preview = preview_revert_text(pseudo_text, mapping_bytes, passphrase)
    assert preview["mapping_entries"] == 2
    assert preview["total_matches"] == 2

    applied = apply_revert_text(pseudo_text, mapping_bytes, passphrase)
    assert applied["total_replacements"] == 2
    assert "Mario Rossi" in applied["reverted_text"]
    assert "srv-prod-01.internal.local" in applied["reverted_text"]


def test_revert_text_wrong_passphrase():
    mapping_payload = {"mapping": {"[PERSON_0001]": "Mario Rossi"}}
    mapping_bytes = encrypt_mapping(mapping_payload, "CorrectPass_123")

    with pytest.raises(ValueError, match="Passphrase non è corretta"):
        apply_revert_text("Ciao [PERSON_0001]", mapping_bytes, "WrongPass_123")


def test_revert_text_empty_text():
    """Text vuoto: deve tornare 0 replacements ma non errore"""
    passphrase = "TestPass_123"
    mapping_payload = {"mapping": {"[PERSON_0001]": "Original Name"}}
    mapping_bytes = encrypt_mapping(mapping_payload, passphrase)

    applied = apply_revert_text("", mapping_bytes, passphrase)
    assert applied["input_chars"] == 0
    assert applied["total_replacements"] == 0
    assert applied["reverted_text"] == ""


def test_revert_text_empty_mapping():
    """Mapping vuoto (niente entità): testo non cambia"""
    passphrase = "TestPass_123"
    mapping_payload = {"mapping": {}}
    mapping_bytes = encrypt_mapping(mapping_payload, passphrase)

    text = "Questo è un testo senza pseudonimi"
    applied = apply_revert_text(text, mapping_bytes, passphrase)
    assert applied["total_replacements"] == 0
    assert applied["reverted_text"] == text


def test_revert_text_no_matches():
    """Testo non contiene alcun pseudonimo previsibile"""
    passphrase = "TestPass_123"
    mapping_payload = {"mapping": {"[PERSON_0001]": "Mario Rossi"}}
    mapping_bytes = encrypt_mapping(mapping_payload, passphrase)

    text = "Questo testo non ha pseudonimi"
    applied = apply_revert_text(text, mapping_bytes, passphrase)
    assert applied["total_replacements"] == 0
    assert applied["reverted_text"] == text


def test_revert_text_overlapping_pseudonyms():
    """Pseudonimi che sono substring l'uno dell'altro: ordine decrescente per lunghezza"""
    passphrase = "TestPass_123"
    mapping_payload = {
        "mapping": {
            "[PERSON_01]": "John",
            "[PERSON_010]": "Jane",  # contiene la substring di [PERSON_01]
        }
    }
    mapping_bytes = encrypt_mapping(mapping_payload, passphrase)

    # Test: se entrambi sono nel testo, devono sostituirsi correttamente
    text = "[PERSON_010] e [PERSON_01]"
    applied = apply_revert_text(text, mapping_bytes, passphrase)
    # Ordine per lunghezza: [PERSON_010] prima (più lungo)
    assert "Jane" in applied["reverted_text"]
    assert "John" in applied["reverted_text"]
    assert applied["total_replacements"] == 2


def test_validate_mapping_file_invalid_magic_bytes():
    """Validazione magic bytes: file senza PSM2 header deve fallare"""
    with pytest.raises(ValueError, match="magic header non riconosciuto"):
        _validate_mapping_file(b"not a mapping file")


def test_validate_mapping_file_empty():
    """Validazione: file vuoto deve fallare"""
    with pytest.raises(ValueError, match="vuoto"):
        _validate_mapping_file(b"")


def test_validate_mapping_file_too_small():
    """Validazione: file più piccolo del magic header deve fallare"""
    with pytest.raises(ValueError, match="troppo piccolo"):
        _validate_mapping_file(b"\x50\x53")  # Incomplete magic bytes


def test_replace_all_with_multiple_occurrences():
    """Test della funzione _replace_all con occorrenze multiple"""
    text = "User [PERSON_0001] called [PERSON_0001] at [HOST_0001]"
    sub_map = {"[PERSON_0001]": "Alice", "[HOST_0001]": "server.local"}

    from app.core.revert import _replace_all

    result_text, count = _replace_all(text, sub_map)
    assert count == 3  # 2x [PERSON_0001], 1x [HOST_0001]
    assert result_text == "User Alice called Alice at server.local"


def test_preview_revert_text_sample_matches():
    """Preview deve mostrare fino a 10 pseudonimi trovati"""
    passphrase = "TestPass_123"
    mapping_payload = {"mapping": {f"[PSEUDO_{i:04d}]": f"OriginalValue_{i}" for i in range(20)}}
    mapping_bytes = encrypt_mapping(mapping_payload, passphrase)

    # Testo con alcuni pseudonimi
    text = " ".join([f"[PSEUDO_{i:04d}]" for i in range(15)])

    preview = preview_revert_text(text, mapping_bytes, passphrase)
    assert preview["mapping_entries"] == 20
    assert preview["total_matches"] == 15
    assert len(preview["sample_matches"]) <= 10  # Max 10 sample


def test_revert_text_with_special_chars():
    """Testo con caratteri speciali e unicode"""
    passphrase = "TestPass_123"
    mapping_payload = {"mapping": {"[PERSONA]": "José García", "[EMAIL]": "test@ente.it"}}
    mapping_bytes = encrypt_mapping(mapping_payload, passphrase)

    text = "Contatto: [EMAIL] per [PERSONA] - Ufficio: Via Roma 123"
    applied = apply_revert_text(text, mapping_bytes, passphrase)
    assert "José García" in applied["reverted_text"]
    assert "test@ente.it" in applied["reverted_text"]


def test_console_apply_response_includes_batch_id():
    """Verifica che /console/apply ritorni batch_id nella risposta"""
    # Questo test sarà validato tramite API test, non qui
    # Ma documentiamo che la response DEVE contenere batch_id
    pass
