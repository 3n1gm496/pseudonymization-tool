"""
Modulo di trasformazione: applica le sostituzioni ai file originali
in base alle decisioni di review dell'utente.
"""
import re
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional

from app.models.schemas import Finding, ReviewAction, FileRecord, FileStatus
from app.parsers.base import ParseResult

logger = logging.getLogger(__name__)


def _build_substitution_map(findings: List[Finding]) -> Dict[str, str]:
    """
    Costruisce una mappa {valore_originale: pseudonimo_finale}
    in base alle decisioni di review.
    I finding con azione REJECT vengono esclusi.
    """
    sub_map: Dict[str, str] = {}
    for finding in findings:
        if finding.review_action == ReviewAction.REJECT:
            continue
        final = finding.final_pseudonym
        if finding.original_value not in sub_map:
            sub_map[finding.original_value] = final
    return sub_map


def _apply_substitutions_to_text(text: str, sub_map: Dict[str, str]) -> str:
    """
    Applica le sostituzioni a una stringa di testo.
    Ordina le chiavi per lunghezza decrescente per evitare sostituzioni parziali.
    """
    if not sub_map:
        return text

    # Ordina per lunghezza decrescente (sostituisce prima le stringhe più lunghe)
    sorted_keys = sorted(sub_map.keys(), key=len, reverse=True)
    result = text
    for original in sorted_keys:
        pseudonym = sub_map[original]
        # Usa re.sub per una sostituzione case-sensitive precisa
        result = result.replace(original, pseudonym)
    return result


def transform_text_file(
    original_path: Path,
    output_path: Path,
    findings: List[Finding],
) -> List[str]:
    """Trasforma un file di testo semplice (.txt, .md, .csv)."""
    warnings = []
    sub_map = _build_substitution_map(findings)

    try:
        try:
            content = original_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = original_path.read_text(encoding="latin-1")
            warnings.append("File letto con codifica latin-1.")

        transformed = _apply_substitutions_to_text(content, sub_map)
        output_path.write_text(transformed, encoding="utf-8")
    except Exception as e:
        warnings.append(f"Errore durante la trasformazione del file di testo: {e}")

    return warnings


def transform_docx_file(
    original_path: Path,
    output_path: Path,
    findings: List[Finding],
) -> List[str]:
    """Trasforma un file .docx."""
    warnings = []
    sub_map = _build_substitution_map(findings)

    try:
        from docx import Document
        doc = Document(str(original_path))

        # Trasforma paragrafi
        for para in doc.paragraphs:
            if para.text.strip():
                for run in para.runs:
                    run.text = _apply_substitutions_to_text(run.text, sub_map)

        # Trasforma tabelle
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            run.text = _apply_substitutions_to_text(run.text, sub_map)

        # Trasforma header e footer
        for section in doc.sections:
            for part in [section.header, section.footer]:
                if part:
                    for para in part.paragraphs:
                        for run in para.runs:
                            run.text = _apply_substitutions_to_text(run.text, sub_map)

        doc.save(str(output_path))
        warnings.append("LIMITE MVP: Commenti, note a piè di pagina e caselle di testo non sono stati processati.")

    except Exception as e:
        warnings.append(f"Errore durante la trasformazione del file DOCX: {e}")

    return warnings


def transform_xlsx_file(
    original_path: Path,
    output_path: Path,
    findings: List[Finding],
) -> List[str]:
    """Trasforma un file .xlsx (solo celle testuali, formule intatte)."""
    warnings = []
    sub_map = _build_substitution_map(findings)

    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(original_path))

        modified_cells = 0
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row in ws.iter_rows():
                for cell in row:
                    # Non toccare le formule
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        continue
                    if isinstance(cell.value, str) and cell.value.strip():
                        new_value = _apply_substitutions_to_text(cell.value, sub_map)
                        if new_value != cell.value:
                            cell.value = new_value
                            modified_cells += 1

        wb.save(str(output_path))
        warnings.append(f"Modificate {modified_cells} celle testuali. Le formule sono state preservate.")

    except Exception as e:
        warnings.append(f"Errore durante la trasformazione del file XLSX: {e}")

    return warnings


def transform_pdf_file(
    original_path: Path,
    output_path: Path,
    findings: List[Finding],
) -> List[str]:
    """
    Per i PDF, non è possibile modificare il file originale in modo affidabile
    senza strumenti avanzati. Generiamo un file .txt con il testo pseudonimizzato.
    """
    warnings = []
    sub_map = _build_substitution_map(findings)

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(original_path))

        all_text = []
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            transformed_text = _apply_substitutions_to_text(page_text, sub_map)
            all_text.append(f"--- Pagina {page_num} ---\n{transformed_text}")

        # Output come file .txt pseudonimizzato
        txt_output_path = output_path.with_suffix(".pseudonymized.txt")
        txt_output_path.write_text("\n\n".join(all_text), encoding="utf-8")

        warnings.append(
            "NOTA: Per i file PDF, l'output è un file .txt con il testo pseudonimizzato. "
            "La modifica diretta del PDF non è supportata nell'MVP."
        )

    except Exception as e:
        warnings.append(f"Errore durante la trasformazione del file PDF: {e}")

    return warnings


def transform_image_file(
    original_path: Path,
    output_path: Path,
    findings: List[Finding],
    parse_result: Optional[ParseResult] = None,
) -> List[str]:
    """
    Applica la redazione visuale (box di oscuramento) sull'immagine
    per le entità trovate tramite OCR.
    """
    warnings = []

    try:
        from PIL import Image, ImageDraw

        # Usa l'immagine già pulita dall'EXIF se disponibile
        source_path = parse_result.image_path if parse_result and parse_result.image_path else original_path
        img = Image.open(str(source_path))
        draw = ImageDraw.Draw(img)

        redacted_count = 0
        for finding in findings:
            if finding.review_action == ReviewAction.REJECT:
                continue
            bbox = finding.location.bbox
            if bbox and len(bbox) == 4:
                x, y, w, h = bbox
                # Disegna un rettangolo nero di redazione
                draw.rectangle([x, y, x + w, y + h], fill="black", outline="black")
                redacted_count += 1

        img.save(str(output_path))
        warnings.append(f"Redazione visuale applicata: {redacted_count} aree oscurate.")

        if redacted_count == 0 and findings:
            warnings.append(
                "ATTENZIONE: Nessuna area di redazione visuale applicata. "
                "Le entità trovate potrebbero non avere coordinate bounding box precise."
            )

    except Exception as e:
        warnings.append(f"Errore durante la redazione visuale dell'immagine: {e}")

    return warnings


def transform_file(
    original_path: Path,
    output_dir: Path,
    findings: List[Finding],
    parse_result: Optional[ParseResult] = None,
) -> tuple[Path, List[str]]:
    """
    Dispatcher principale: seleziona la funzione di trasformazione appropriata
    in base all'estensione del file.

    Restituisce (output_path, warnings).
    """
    ext = original_path.suffix.lower()
    output_path = output_dir / original_path.name
    warnings: List[str] = []

    if ext in (".txt", ".md", ".csv"):
        warnings = transform_text_file(original_path, output_path, findings)

    elif ext == ".docx":
        warnings = transform_docx_file(original_path, output_path, findings)

    elif ext == ".xlsx":
        warnings = transform_xlsx_file(original_path, output_path, findings)

    elif ext == ".pdf":
        warnings = transform_pdf_file(original_path, output_path, findings)
        # L'output effettivo è il .txt, aggiorna il path
        txt_path = output_path.with_suffix(".pseudonymized.txt")
        if txt_path.exists():
            output_path = txt_path

    elif ext in (".jpg", ".jpeg", ".png"):
        warnings = transform_image_file(original_path, output_path, findings, parse_result)

    else:
        # Formato non supportato: copia il file originale con warning
        shutil.copy2(str(original_path), str(output_path))
        warnings.append(f"Formato '{ext}' non supportato per la trasformazione. File copiato senza modifiche.")

    return output_path, warnings
