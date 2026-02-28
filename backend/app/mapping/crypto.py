"""
Modulo di cifratura e decifratura del mapping di reversibilità.
Utilizza AES-256-GCM con PBKDF2 per la derivazione della chiave dalla passphrase.
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

# Parametri di cifratura
PBKDF2_ITERATIONS = 600_000  # NIST raccomanda >= 600k per SHA-256 nel 2023
SALT_SIZE = 32  # 256 bit
NONCE_SIZE = 12  # 96 bit (standard per AES-GCM)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """
    Deriva una chiave AES-256 dalla passphrase usando PBKDF2-HMAC-SHA256.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bit
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_mapping(data: Dict[str, Any], passphrase: str) -> bytes:
    """
    Cifra un dizionario Python in un blob binario usando AES-256-GCM.

    Formato del file cifrato:
    [salt (32 bytes)] [nonce (12 bytes)] [ciphertext + tag (variabile)]
    """
    # Serializza i dati in JSON
    plaintext = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    # Genera salt e nonce casuali
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)

    # Deriva la chiave
    key = _derive_key(passphrase, salt)

    # Cifra con AES-GCM (include autenticazione)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Concatena: salt + nonce + ciphertext
    return salt + nonce + ciphertext


def decrypt_mapping(encrypted_data: bytes, passphrase: str) -> Dict[str, Any]:
    """
    Decifra un blob binario e restituisce il dizionario originale.

    Solleva:
    - ValueError: se il formato del file è invalido.
    - cryptography.exceptions.InvalidTag: se la passphrase è errata o i dati sono corrotti.
    """
    if len(encrypted_data) < SALT_SIZE + NONCE_SIZE + 16:  # 16 = min GCM tag size
        raise ValueError("File di mapping non valido o corrotto (dimensione insufficiente).")

    # Estrai i componenti
    salt = encrypted_data[:SALT_SIZE]
    nonce = encrypted_data[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
    ciphertext = encrypted_data[SALT_SIZE + NONCE_SIZE:]

    # Deriva la chiave
    key = _derive_key(passphrase, salt)

    # Decifra
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise InvalidTag("Passphrase errata o file di mapping corrotto.")

    # Deserializza JSON
    return json.loads(plaintext.decode("utf-8"))


def save_encrypted_mapping(data: Dict[str, Any], passphrase: str, output_path: Path) -> None:
    """Cifra i dati e li salva su file."""
    encrypted = encrypt_mapping(data, passphrase)
    output_path.write_bytes(encrypted)
    logger.info("Mapping cifrato salvato in: %s", output_path)


def load_and_decrypt_mapping(file_path: Path, passphrase: str) -> Dict[str, Any]:
    """Legge un file di mapping cifrato e lo decifra."""
    encrypted_data = file_path.read_bytes()
    return decrypt_mapping(encrypted_data, passphrase)
