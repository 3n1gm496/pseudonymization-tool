import io
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.mapping.crypto import decrypt_mapping

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".conf"}


def _is_text_file(name: str) -> bool:
    return Path(name).suffix.lower() in TEXT_EXTENSIONS


def _safe_decode(data: bytes) -> Tuple[str, str]:
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def _build_sub_map(mapping_data: Dict[str, Any]) -> Dict[str, str]:
    mapping = mapping_data.get("mapping", {}) if isinstance(mapping_data, dict) else {}
    if not isinstance(mapping, dict):
        return {}
    return {str(k): str(v) for k, v in mapping.items()}


def _replace_all(text: str, sub_map: Dict[str, str]) -> Tuple[str, int]:
    if not sub_map:
        return text, 0

    ordered_keys = sorted(sub_map.keys(), key=len, reverse=True)
    total = 0
    out = text
    for pseudo in ordered_keys:
        original = sub_map[pseudo]
        occurrences = out.count(pseudo)
        if occurrences > 0:
            out = out.replace(pseudo, original)
            total += occurrences
    return out, total


def _extract_mapping_from_zip(zip_bytes: bytes, passphrase: str) -> Dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        if "mapping.enc" not in zf.namelist():
            raise ValueError("Il file ZIP non contiene mapping.enc")
        enc_data = zf.read("mapping.enc")
    return decrypt_mapping(enc_data, passphrase)


def _validate_mapping_file(mapping_bytes: bytes) -> None:
    if not mapping_bytes:
        raise ValueError("Il file mapping.enc è vuoto")
    if len(mapping_bytes) < 5:
        raise ValueError("Il file è troppo piccolo per essere un mapping.enc valido")
    if not mapping_bytes.startswith(b"\x50\x53\x4D\x32"):  # PSM2 magic header
        raise ValueError("Il file non è un mapping.enc valido (magic header non riconosciuto)")


def extract_mapping_from_encrypted(mapping_bytes: bytes, passphrase: str) -> Dict[str, Any]:
    from cryptography.exceptions import InvalidTag

    _validate_mapping_file(mapping_bytes)
    if not passphrase.strip():
        raise ValueError("La passphrase è obbligatoria")
    try:
        return decrypt_mapping(mapping_bytes, passphrase.strip())
    except ValueError as e:
        if "Passphrase errata" in str(e):
            raise ValueError("Passphrase non è corretta per questo mapping.enc")
        raise
    except InvalidTag:
        raise ValueError("Passphrase non è corretta per questo mapping.enc")


def preview_revert_text(text: str, mapping_bytes: bytes, passphrase: str) -> Dict[str, Any]:
    mapping_data = extract_mapping_from_encrypted(mapping_bytes, passphrase)
    sub_map = _build_sub_map(mapping_data)

    if not text:
        return {
            "mapping_entries": len(sub_map),
            "input_chars": 0,
            "total_matches": 0,
            "sample_matches": [],
            "warning": "Il testo è vuoto",
        }

    total_matches = 0
    sample_matches: List[Dict[str, Any]] = []
    for pseudo in sorted(sub_map.keys(), key=len, reverse=True):
        occurrences = text.count(pseudo)
        if occurrences > 0:
            total_matches += occurrences
            if len(sample_matches) < 10:
                sample_matches.append({"pseudonym": pseudo, "matches": occurrences})

    return {
        "mapping_entries": len(sub_map),
        "input_chars": len(text),
        "total_matches": total_matches,
        "sample_matches": sample_matches,
    }


def apply_revert_text(text: str, mapping_bytes: bytes, passphrase: str) -> Dict[str, Any]:
    mapping_data = extract_mapping_from_encrypted(mapping_bytes, passphrase)
    sub_map = _build_sub_map(mapping_data)

    if not text:
        return {
            "reverted_text": "",
            "total_replacements": 0,
            "mapping_entries": len(sub_map),
            "input_chars": 0,
            "output_chars": 0,
        }

    reverted_text, replacements = _replace_all(text, sub_map)
    return {
        "reverted_text": reverted_text,
        "total_replacements": replacements,
        "mapping_entries": len(sub_map),
        "input_chars": len(text),
        "output_chars": len(reverted_text),
    }


def preview_revert(zip_bytes: bytes, passphrase: str) -> Dict[str, Any]:
    mapping_data = _extract_mapping_from_zip(zip_bytes, passphrase)
    sub_map = _build_sub_map(mapping_data)

    files_scanned = 0
    text_files_scanned = 0
    total_matches = 0
    sample_matches: List[Dict[str, Any]] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for name in zf.namelist():
            if not name.startswith("files/") or name.endswith("/"):
                continue
            files_scanned += 1
            if not _is_text_file(name):
                continue

            text_files_scanned += 1
            content = zf.read(name)
            decoded, _ = _safe_decode(content)

            file_matches = 0
            for pseudo in sub_map.keys():
                c = decoded.count(pseudo)
                file_matches += c
            total_matches += file_matches

            if file_matches > 0 and len(sample_matches) < 10:
                sample_matches.append({"file": name, "matches": file_matches})

    return {
        "mapping_entries": len(sub_map),
        "files_scanned": files_scanned,
        "text_files_scanned": text_files_scanned,
        "total_matches": total_matches,
        "sample_matches": sample_matches,
    }


def apply_revert(zip_bytes: bytes, passphrase: str) -> Tuple[bytes, Dict[str, Any]]:
    mapping_data = _extract_mapping_from_zip(zip_bytes, passphrase)
    sub_map = _build_sub_map(mapping_data)

    input_buffer = io.BytesIO(zip_bytes)
    output_buffer = io.BytesIO()

    processed_files = 0
    reverted_files = 0
    skipped_files = 0
    replacements = 0
    warnings: List[str] = []

    with zipfile.ZipFile(input_buffer, "r") as zin, zipfile.ZipFile(output_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            data = zin.read(name)

            if name.startswith("files/") and not name.endswith("/"):
                processed_files += 1
                if _is_text_file(name):
                    decoded, encoding = _safe_decode(data)
                    reverted_text, count = _replace_all(decoded, sub_map)
                    if count > 0:
                        reverted_files += 1
                        replacements += count
                    zout.writestr(name, reverted_text.encode(encoding, errors="replace"))
                else:
                    skipped_files += 1
                    warnings.append(f"File non testuale copiato senza revert: {name}")
                    zout.writestr(name, data)
            else:
                zout.writestr(name, data)

        summary = {
            "processed_files": processed_files,
            "reverted_files": reverted_files,
            "skipped_files": skipped_files,
            "total_replacements": replacements,
            "mapping_entries": len(sub_map),
            "warnings": warnings[:50],
        }
        zout.writestr("revert_report.json", json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"))

    return output_buffer.getvalue(), summary
