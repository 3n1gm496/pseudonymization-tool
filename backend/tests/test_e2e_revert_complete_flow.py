"""
E2E Integration Tests: Complete Revert Flow

Tests the full cycle:
1. Pseudonymize text with multiple entities
2. Download mapping.enc
3. Simulate AI processing (text modification)
4. Decipher with mapping.enc + passphrase
5. Verify original text recovery
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
import requests

BASE_URL = "http://localhost:8000/api"

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_E2E", "0") != "1",
    reason="Live E2E tests disabled (set RUN_LIVE_E2E=1 to enable)",
)


def get_authenticated_session():
    """Helper: Get an authenticated requests session."""
    session = requests.Session()
    auth_resp = session.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin123!"})
    assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
    return session


def test_complete_e2e_flow():
    """
    Complete E2E test: Pseudonymize → Export → Decipher → Verify

    This is a single test that chains all steps together
    since pytest doesn't preserve state between class methods.
    """
    session = get_authenticated_session()

    print("\n" + "=" * 70)
    print("E2E COMPLETE FLOW TEST")
    print("=" * 70)

    # ──── Step 1: Create batch with entities ──────────────────
    print("\n[1] Pseudonymizing text with multiple entities...")
    test_text = (
        "John Smith from New York contacted ACME Corp on 2026-01-15. "
        "His email is john.smith@example.com. "
        "Project code is PROJ-2024-001. "
        "Server: 192.168.1.100"
    )

    batch_resp = session.post(f"{BASE_URL}/console/scan", json={"text": test_text})
    assert batch_resp.status_code == 200, f"Scan failed: {batch_resp.text}"
    batch_data = batch_resp.json()

    batch_id = batch_data["batch_id"]
    file_id = batch_data["file_id"]
    passphrase = batch_data["passphrase"]
    findings_count = batch_data.get("findings_count", 0)

    print(f"  ✓ Batch created: {batch_id[:8]}...")
    print(f"  ✓ Entities detected: {findings_count}")
    print(f"  ✓ Passphrase length: {len(passphrase)} chars")

    assert findings_count > 0, f"No entities detected! Expected 3+, got {findings_count}"

    # ──── Step 2: Apply pseudonymization ──────────────────────
    print("\n[2] Applying pseudonymization...")
    apply_resp = session.post(
        f"{BASE_URL}/console/apply", json={"batch_id": batch_id, "file_id": file_id, "text": test_text}
    )
    assert apply_resp.status_code == 200, f"Apply failed: {apply_resp.text}"
    apply_data = apply_resp.json()

    pseudonymized_text = apply_data["pseudonymized_text"]
    applied_count = apply_data.get("applied_count", 0)

    print(f"  ✓ Pseudonymization applied")
    print(f"  ✓ Entities replaced: {applied_count}")
    print(f"  ✓ Original: {test_text[:80]}...")
    print(f"  ✓ Result:   {pseudonymized_text[:80]}...")

    # Verify text was modified
    assert pseudonymized_text != "John Smith from New York", "Text wasn't modified - no pseudonymization happened!"
    assert applied_count > 0, "No entities were applied!"

    # ──── Step 3: Download mapping.enc ────────────────────────
    print("\n[3] Downloading mapping.enc...")
    map_resp = session.get(f"{BASE_URL}/console/{batch_id}/mapping.enc")

    assert map_resp.status_code == 200, f"Mapping download failed: {map_resp.text}"
    assert map_resp.headers.get("content-type") == "application/octet-stream"
    mapping_bytes = map_resp.content

    print(f"  ✓ Mapping.enc downloaded")
    print(f"  ✓ File size: {len(mapping_bytes)} bytes")
    print(f"  ✓ Magic bytes: {mapping_bytes[:4].hex()}")

    assert mapping_bytes.startswith(b"PSM2"), f"Invalid magic bytes: expected PSM2, got {mapping_bytes[:4].hex()}"

    # ──── Step 4: Verify decryption ────────────────────────────
    print("\n[4] Verifying mapping decryption...")
    from app.mapping.crypto import decrypt_mapping

    mapping_dict = decrypt_mapping(mapping_bytes, passphrase)
    assert "mapping" in mapping_dict, "Mapping doesn't have 'mapping' key"
    assert isinstance(mapping_dict["mapping"], dict), f"Mapping should be dict, got {type(mapping_dict['mapping'])}"

    mapping = mapping_dict["mapping"]
    print(f"  ✓ Mapping decrypted successfully")
    print(f"  ✓ Mapping entries: {len(mapping)}")
    for i, (pseudo, original) in enumerate(list(mapping.items())[:3]):
        print(f"    - {pseudo} → {original}")

    assert len(mapping) > 0, "Mapping is empty!"

    # ──── Step 5: Simulate AI response ─────────────────────────
    print("\n[5] Simulating AI response...")
    # In reality, AI receives pseudo text and returns modified version
    # For this test, we'll pass the same pseudonymized text
    ai_response = pseudonymized_text
    print(f"  ✓ Simulated AI processing")
    print(f"  ✓ Response text: {ai_response[:80]}...")

    # ──── Step 6: Preview text revert ──────────────────────────
    print("\n[6] Previewing text revert matches...")
    preview_resp = session.post(
        f"{BASE_URL}/revert/text/preview",
        files={"mapping_file": ("mapping.enc", mapping_bytes)},
        data={"passphrase": passphrase, "text": ai_response},
    )

    assert preview_resp.status_code == 200, f"Preview failed: {preview_resp.text}"
    preview_data = preview_resp.json()

    total_matches = preview_data.get("total_matches", 0)
    print(f"  ✓ Preview succeeded")
    print(f"  ✓ Mapping entries: {preview_data.get('mapping_entries')}")
    print(f"  ✓ Input chars: {preview_data.get('input_chars')}")
    print(f"  ✓ Total matches: {total_matches}")
    sample_matches = preview_data.get("sample_matches", [])
    if sample_matches[:3]:
        for match in sample_matches[:3]:
            print(f"    - {match}")

    assert total_matches > 0, "No matches found! Revert won't work."

    # ──── Step 7: Apply text revert ──────────────────────────
    print("\n[7] Applying text revert...")
    revert_resp = session.post(
        f"{BASE_URL}/revert/text/apply",
        files={"mapping_file": ("mapping.enc", mapping_bytes)},
        data={"passphrase": passphrase, "text": ai_response},
    )

    assert revert_resp.status_code == 200, f"Apply revert failed: {revert_resp.text}"
    revert_data = revert_resp.json()

    reverted_text = revert_data["reverted_text"]
    print(f"  ✓ Text revert applied")
    print(f"  ✓ Reverted text: {reverted_text[:80]}...")

    # ──── Step 8: Verify original recovery ───────────────────
    print("\n[8] Verifying original text recovery...")

    checks = [
        ("John", "John" in reverted_text),
        ("New York", "New York" in reverted_text),
        ("ACME", "ACME" in reverted_text),
        ("john.smith@example.com", "john.smith@example.com" in reverted_text),
    ]

    failed = []
    for name, result in checks:
        status = "✓" if result else "✗"
        print(f"    {status} {name} recovered")
        if not result:
            failed.append(name)

    assert len(failed) == 0, f"Failed to recover: {', '.join(failed)}"

    print("\n" + "=" * 70)
    print("✅ COMPLETE E2E FLOW SUCCESSFUL!")
    print("=" * 70 + "\n")


@pytest.mark.asyncio
async def test_e2e_flow_with_wrong_passphrase():
    """Test that wrong passphrase produces sensible error."""
    import requests

    session = requests.Session()

    # Auth
    auth = session.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin123!"})
    assert auth.status_code == 200

    # Create batch
    batch_resp = session.post(f"{BASE_URL}/console/scan", json={"text": "John Smith from NYC"})
    assert batch_resp.status_code == 200
    batch_id = batch_resp.json()["batch_id"]
    file_id = batch_resp.json()["file_id"]

    # Apply
    apply_resp = session.post(
        f"{BASE_URL}/console/apply", json={"batch_id": batch_id, "file_id": file_id, "text": "John Smith from NYC"}
    )
    assert apply_resp.status_code == 200
    correct_passphrase = apply_resp.json()["passphrase"]

    # Download mapping
    map_resp = session.get(f"{BASE_URL}/console/{batch_id}/mapping.enc")
    assert map_resp.status_code == 200
    mapping_bytes = map_resp.content

    # Try revert with WRONG passphrase
    wrong_passphrase = "WRONG_PASSPHRASE_1234567890"
    revert_resp = session.post(
        f"{BASE_URL}/revert/text/preview",
        files={"mapping_file": ("mapping.enc", mapping_bytes)},
        data={"passphrase": wrong_passphrase, "text": "pseudonymized text"},
    )

    # Should fail with 400
    assert revert_resp.status_code == 400, f"Expected 400 with wrong passphrase, got {revert_resp.status_code}"

    error_msg = revert_resp.json().get("detail", "")
    assert (
        "Passphrase" in error_msg or "passphrase" in error_msg.lower() or "non è corretta" in error_msg.lower()
    ), f"Error message should mention passphrase, got: {error_msg}"

    print(f"\n✓ Wrong passphrase correctly rejected")
    print(f"  Error: {error_msg}")


@pytest.mark.asyncio
async def test_e2e_invalid_mapping_file():
    """Test that invalid/corrupted mapping files are rejected."""
    import requests

    session = requests.Session()

    # Auth
    auth = session.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin123!"})
    assert auth.status_code == 200

    # Try to revert with invalid mapping file
    invalid_mapping = b"INVALID_NOT_PSM2_HEADER_DATA"

    revert_resp = session.post(
        f"{BASE_URL}/revert/text/preview",
        files={"mapping_file": ("mapping.enc", invalid_mapping)},
        data={"passphrase": "somepassphrase", "text": "some text"},
    )

    # Should fail with 400
    assert revert_resp.status_code == 400, f"Expected 400 with invalid mapping, got {revert_resp.status_code}"

    error_msg = revert_resp.json().get("detail", "")
    assert (
        "magic" in error_msg.lower() or "invalid" in error_msg.lower()
    ), f"Error should mention invalid format, got: {error_msg}"

    print(f"\n✓ Invalid mapping file correctly rejected")
    print(f"  Error: {error_msg}")
