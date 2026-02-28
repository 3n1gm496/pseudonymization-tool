"""
Parser per file .pdf (solo PDF nativamente testuali).
I PDF basati su immagini o cifrati vengono segnalati con warning.
"""
from pathlib import Path
from typing import List

from app.parsers.base import BaseParser, ParseResult, TextChunk


class PdfParser(BaseParser):
    """Parser per file PDF testuali."""

    @property
    def supported_extensions(self) -> List[str]:
        return [".pdf"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult(file_path=file_path)
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))

            # Controlla se il PDF è cifrato
            if reader.is_encrypted:
                result.success = False
                result.error_message = (
                    "Il file PDF è cifrato/protetto da password. "
                    "Non è possibile estrarre il testo. "
                    "ATTENZIONE: il file NON è stato processato."
                )
                return result

            total_pages = len(reader.pages)
            pages_with_text = 0
            total_chars = 0

            for page_num, page in enumerate(reader.pages, start=1):
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        pages_with_text += 1
                        total_chars += len(page_text)
                        # Suddividi per riga
                        for line_num, line in enumerate(page_text.splitlines(), start=1):
                            if line.strip():
                                result.chunks.append(
                                    TextChunk(
                                        text=line,
                                        source_ref=f"pagina {page_num}, riga {line_num}",
                                        line_number=line_num,
                                    )
                                )
                except Exception as page_err:
                    result.warnings.append(f"Errore nell'estrazione del testo dalla pagina {page_num}: {page_err}")

            # Valuta se il PDF è "testuale" o basato su immagini
            if pages_with_text == 0:
                result.success = False
                result.error_message = (
                    f"Il PDF non contiene testo estraibile ({total_pages} pagine analizzate). "
                    f"Potrebbe essere un PDF basato su immagini (scansione). "
                    f"ATTENZIONE: il file NON è stato processato. "
                    f"L'OCR su PDF scansionati è previsto in una fase successiva della roadmap."
                )
                return result

            if pages_with_text < total_pages:
                result.warnings.append(
                    f"Solo {pages_with_text}/{total_pages} pagine contengono testo estraibile. "
                    f"Le pagine senza testo potrebbero contenere immagini con dati sensibili non rilevati."
                )

        except Exception as e:
            result.success = False
            result.error_message = f"Errore durante il parsing del file PDF: {e}"

        return result
