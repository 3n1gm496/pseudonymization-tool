"""
Factory per la selezione del parser appropriato in base all'estensione del file.
"""

from pathlib import Path
from typing import Optional

from app.parsers.base import BaseParser, ParseResult
from app.parsers.docx_parser import DocxParser
from app.parsers.image_parser import ImageParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.text_parser import TextParser
from app.parsers.xlsx_parser import XlsxParser

_PARSERS = [
    TextParser(),
    DocxParser(),
    XlsxParser(),
    PdfParser(),
    ImageParser(),
]

# Mappa estensione -> parser
_EXTENSION_MAP = {}
for parser in _PARSERS:
    for ext in parser.supported_extensions:
        _EXTENSION_MAP[ext.lower()] = parser


def get_parser(file_path: Path) -> Optional[BaseParser]:
    """Restituisce il parser appropriato per il file dato, o None se non supportato."""
    ext = file_path.suffix.lower()
    return _EXTENSION_MAP.get(ext)


def parse_file(file_path: Path) -> ParseResult:
    """
    Seleziona il parser corretto e processa il file.
    In caso di formato non supportato, restituisce un ParseResult con errore.
    """
    parser = get_parser(file_path)
    if parser is None:
        result = ParseResult(file_path=file_path, success=False)
        result.error_message = (
            f"Formato file non supportato: '{file_path.suffix}'. "
            f"Formati supportati: {', '.join(sorted(_EXTENSION_MAP.keys()))}."
        )
        return result
    return parser.parse(file_path)
