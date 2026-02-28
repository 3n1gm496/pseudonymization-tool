"""
Modulo di cifratura e decifratura del mapping di reversibilità.
Utilizza AES-256-GCM con PBKDF2 per la derivazione della chiave dalla passphrase.

Formato file cifrato v2 (GATE 5):
  [MAGIC (4 bytes: 0x50534D32)] [VERSION (1 byte: 0x02)]
  [salt (32 bytes)] [nonce (12 bytes)] [ciphertext + GCM tag (variabile)]

Formato file cifrato v1 (legacy, compatibilità retroattiva):
  [salt (32 bytes)] [nonce (12 bytes)] [ciphertext + GCM tag]
  (nessun magic header — rilevato per dimensione e assenza del magic)
"""
import json
import os
import secrets
import string
import logging
from pathlib import Path
from typing import Dict, Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

# ─── Costanti ────────────────────────────────────────────────────────────────
PBKDF2_ITERATIONS = 600_000   # NIST raccomanda >= 600k per SHA-256 (2023)
SALT_SIZE  = 32               # 256 bit
NONCE_SIZE = 12               # 96 bit (standard AES-GCM)

# Magic header per il formato v2
MAGIC_BYTES = b'\x50\x53\x4D\x32'  # "PSM2" in ASCII
FORMAT_VERSION = b'\x02'
HEADER_SIZE = len(MAGIC_BYTES) + len(FORMAT_VERSION)  # 5 bytes

# Alfabeto per la passphrase: esclude caratteri ambigui (0/O, 1/l/I)
_PASSPHRASE_ALPHABET = (
    string.ascii_uppercase.replace('O', '').replace('I', '') +
    string.ascii_lowercase.replace('o', '').replace('l', '') +
    string.digits.replace('0', '').replace('1', '') +
    '-_'
)


def generate_passphrase(length: int = 32) -> str:
    """
    Genera una passphrase crittograficamente sicura usando secrets.choice.
    Lunghezza default: 32 caratteri (~190 bit di entropia con l'alfabeto usato).
    Esclude caratteri visivamente ambigui (0/O, 1/l/I).
    """
    return ''.join(secrets.choice(_PASSPHRASE_ALPHABET) for _ in range(length))


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Deriva una chiave AES-256 dalla passphrase usando PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_mapping(data: Dict[str, Any], passphrase: str) -> bytes:
    """
    Cifra un dizionario Python in un blob binario usando AES-256-GCM.

    Formato v2:
      [MAGIC (4 bytes)] [VERSION (1 byte)] [salt (32 bytes)] [nonce (12 bytes)]
      [ciphertext + GCM tag (variabile)]
    """
    plaintext = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    salt  = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key   = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    # Header v2: magic + version + salt + nonce + ciphertext
    return MAGIC_BYTES + FORMAT_VERSION + salt + nonce + ciphertext


def decrypt_mapping(encrypted_data: bytes, passphrase: str) -> Dict[str, Any]:
    """
    Decifra un blob binario e restituisce il dizionario originale.
    Supporta sia il formato v2 (con magic header) che il formato v1 (legacy).

    Solleva:
    - ValueError: se il formato è invalido o non riconosciuto.
    - cryptography.exceptions.InvalidTag: se la passphrase è errata o i dati sono corrotti.
    """
    # Rilevamento formato
    if encrypted_data[:len(MAGIC_BYTES)] == MAGIC_BYTES:
        # Formato v2
        version = encrypted_data[len(MAGIC_BYTES):HEADER_SIZE]
        if version != FORMAT_VERSION:
            raise ValueError(f"Versione formato mapping non supportata: {version.hex()}")
        offset = HEADER_SIZE
    else:
        # Formato v1 (legacy): nessun magic header
        offset = 0

    min_size = offset + SALT_SIZE + NONCE_SIZE + 16
    if len(encrypted_data) < min_size:
        raise ValueError("File di mapping non valido o corrotto (dimensione insufficiente).")

    salt       = encrypted_data[offset : offset + SALT_SIZE]
    nonce      = encrypted_data[offset + SALT_SIZE : offset + SALT_SIZE + NONCE_SIZE]
    ciphertext = encrypted_data[offset + SALT_SIZE + NONCE_SIZE:]

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise InvalidTag("Passphrase errata o file di mapping corrotto.")

    return json.loads(plaintext.decode("utf-8"))


def save_encrypted_mapping(data: Dict[str, Any], passphrase: str, output_path: Path) -> None:
    """Cifra i dati e li salva su file."""
    encrypted = encrypt_mapping(data, passphrase)
    output_path.write_bytes(encrypted)
    logger.info("Mapping cifrato v2 salvato in: %s (dimensione: %d bytes)", output_path, len(encrypted))


def load_and_decrypt_mapping(file_path: Path, passphrase: str) -> Dict[str, Any]:
    """Legge un file di mapping cifrato e lo decifra (supporta v1 e v2)."""
    encrypted_data = file_path.read_bytes()
    return decrypt_mapping(encrypted_data, passphrase)
