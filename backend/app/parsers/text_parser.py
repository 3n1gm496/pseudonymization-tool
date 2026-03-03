"""
Parser per file di testo semplice: .txt, .md, .csv
"""

import logging
from pathlib import Path
from typing import List

from app.core.exceptions import FileEncodingError, ParsingError
from app.parsers.base import BaseParser, ParseResult, TextChunk

logger = logging.getLogger(__name__)


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
            except UnicodeDecodeError as ue:  # noqa: F841 — usata come causa nella catena
                try:
                    content = file_path.read_text(encoding="latin-1")
                    result.warnings.append(
                        "Il file non era in UTF-8; letto con codifica latin-1. "
                        "Potrebbero esserci caratteri non corretti."
                    )
                except Exception as fallback_err:
                    # Catena esplicita: fallback_err causato da ue (UnicodeDecodeError originale)
                    raise FileEncodingError(
                        str(file_path), "UTF-8 + latin-1 fallback"
                    ) from fallback_err.__cause__ or ue

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

        except FileEncodingError as e:
            result.success = False
            result.error_message = str(e)
            logger.warning("Encoding error in text parser: %s", e)
        except ParsingError as e:
            result.success = False
            result.error_message = str(e)
            logger.warning("Parsing error in text parser: %s", e)
        except Exception as e:
            result.success = False
            result.error_message = f"Errore durante il parsing del file di testo: {e}"
            logger.error("Unexpected error in text parser: %s", e)

        return result
