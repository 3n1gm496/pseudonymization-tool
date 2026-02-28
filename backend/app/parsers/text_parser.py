"""
Parser per file di testo semplice: .txt, .md, .csv
"""
from pathlib import Path
from typing import List

from app.parsers.base import BaseParser, ParseResult, TextChunk


class TextParser(BaseParser):
    """Parser per file di testo semplice, Markdown e CSV."""

    @property
    def supported_extensions(self) -> List[str]:
        return [".txt", ".md", ".csv"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult(file_path=file_path)
        try:
            # Prova a leggere come UTF-8, poi fallback su latin-1
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = file_path.read_text(encoding="latin-1")
                result.warnings.append(
                    f"Il file non era in UTF-8; letto con codifica latin-1. "
                    f"Potrebbero esserci caratteri non corretti."
                )

            # Suddividi il testo riga per riga per avere informazioni di posizione
            for line_num, line in enumerate(content.splitlines(), start=1):
                if line.strip():  # Salta le righe vuote
                    result.chunks.append(
                        TextChunk(
                            text=line,
                            source_ref=f"riga {line_num}",
                            line_number=line_num,
                        )
                    )

        except Exception as e:
            result.success = False
            result.error_message = f"Errore durante il parsing del file di testo: {e}"

        return result
