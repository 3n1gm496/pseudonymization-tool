"""
Interfaccia base per i detector di entità sensibili.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from app.parsers.base import TextChunk
from app.models.schemas import EntityType


@dataclass
class RawFinding:
    """
    Rappresenta un'entità sensibile trovata da un detector,
    prima dell'assegnazione dello pseudonimo.
    """
    entity_type: EntityType
    original_value: str
    source_chunk: TextChunk
    confidence_score: float
    detector_name: str
    start_pos: int = 0  # Posizione di inizio nel testo del chunk
    end_pos: int = 0    # Posizione di fine nel testo del chunk
    # Per le immagini, il bbox specifico della parola/entità trovata
    entity_bbox: List[float] = field(default_factory=list)


class BaseDetector(ABC):
    """Classe base astratta per tutti i detector."""

    @abstractmethod
    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        """
        Analizza un TextChunk e restituisce una lista di RawFinding.
        Non deve mai sollevare eccezioni non gestite.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome identificativo del detector."""
        ...
