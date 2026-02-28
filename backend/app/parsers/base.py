"""
Interfaccia base per i parser di file.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class TextChunk:
    """
    Rappresenta un frammento di testo estratto da un file.
    Mantiene informazioni sulla posizione per consentire la sostituzione accurata.
    """
    text: str
    source_ref: str = ""       # Riferimento alla sorgente (es. "riga 5", "cella A1", "header")
    line_number: Optional[int] = None
    sheet_name: Optional[str] = None
    cell_ref: Optional[str] = None
    is_formula: bool = False    # Flag per le celle con formule in XLSX (non processare)
    bbox: Optional[List[float]] = None  # Per immagini: [x, y, w, h]


@dataclass
class ParseResult:
    """Risultato del parsing di un singolo file."""
    file_path: Path
    chunks: List[TextChunk] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_image: bool = False
    image_path: Optional[Path] = None  # Percorso dell'immagine originale (per la redazione visuale)
    success: bool = True
    error_message: Optional[str] = None


class BaseParser(ABC):
    """Classe base astratta per tutti i parser."""

    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        """
        Esegue il parsing del file e restituisce un ParseResult.
        Non deve mai sollevare eccezioni non gestite; gli errori vanno
        catturati e inseriti nel ParseResult.
        """
        ...

    def supports_streaming(self) -> bool:
        """Indica se il parser supporta streaming per file grandi."""
        return False

    def parse_stream(self, file_path: Path, chunk_size: int = 1000):
        """
        Generator per parsing incrementale di file grandi.
        Yield TextChunk man mano che vengono estratti.
        Default: fallback a parse() normale.
        """
        result = self.parse(file_path)
        if result.success:
            for chunk in result.chunks:
                yield chunk

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """Lista delle estensioni di file supportate (es. ['.txt', '.md'])."""
        ...
