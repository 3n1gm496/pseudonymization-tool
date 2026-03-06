"""
Motore di pseudonimizzazione.
Genera pseudonimi consistenti per batch in modalità Light e Strict.
"""

import logging
import re
from collections import defaultdict
from typing import Dict, List

from app.detectors.base import RawFinding
from app.models.schemas import BatchMode, EntityType, Finding, FindingLocation

logger = logging.getLogger(__name__)


class PseudonymEngine:
    """
    Genera e gestisce pseudonimi per un singolo batch.
    Garantisce la consistenza: stesso valore originale -> stesso pseudonimo.
    """

    def __init__(self, mode: BatchMode):
        self.mode = mode
        # Mappa: (entity_type, original_value) -> pseudonym
        self._mapping: Dict[tuple, str] = {}
        # Contatori per tipo di entità
        self._counters: Dict[str, int] = defaultdict(int)

    def _next_counter(self, entity_type: str) -> int:
        """Incrementa e restituisce il contatore per un tipo di entità."""
        self._counters[entity_type] += 1
        return self._counters[entity_type]

    def _format_counter(self, n: int) -> str:
        """Formatta il contatore con zero-padding a 3 cifre."""
        return f"{n:03d}"

    def get_or_create_pseudonym(
        self, entity_type: EntityType, original_value: str, canonical_value: str = ""
    ) -> str:
        """
        Restituisce lo pseudonimo per un valore, creandolo se non esiste ancora.

        Se ``canonical_value`` è fornito (es. email normalizzata in lowercase dal
        detector), viene usato come chiave di mapping in modo che varianti con case
        diverso (es. ``User@DOMAIN.com`` e ``user@domain.com``) ricevano lo stesso
        pseudonimo. ``original_value`` viene invece preservato intatto per la
        sostituzione nel testo sorgente (case-sensitive).
        """
        # Usa canonical_value come chiave se disponibile, altrimenti normalizza
        # internamente (retrocompatibilità con detector che non impostano canonical).
        if canonical_value:
            key_value = canonical_value
        elif entity_type == EntityType.EMAIL:
            # Fallback legacy: normalizza solo il dominio
            local, _, domain = original_value.partition("@")
            key_value = f"{local}@{domain.lower()}" if domain else original_value.lower()
        else:
            key_value = original_value

        key = (entity_type, key_value)
        if key not in self._mapping:
            pseudonym = self._generate_pseudonym(entity_type, key_value)
            self._mapping[key] = pseudonym
        return self._mapping[key]

    def _generate_pseudonym(self, entity_type: EntityType, original_value: str) -> str:
        """Genera un nuovo pseudonimo in base al tipo di entità e alla modalità."""
        n = self._next_counter(entity_type.value)
        c = self._format_counter(n)

        if self.mode == BatchMode.LIGHT:
            return self._generate_light(entity_type, original_value, c)
        else:
            return self._generate_strict(entity_type, original_value, c)

    def _generate_light(self, entity_type: EntityType, original_value: str, c: str) -> str:
        """Genera uno pseudonimo in modalità Light (preserva struttura)."""
        if entity_type == EntityType.EMAIL:
            # Preserva TLD e struttura
            parts = original_value.split("@")
            if len(parts) == 2:
                domain_parts = parts[1].split(".")
                # Preserva il TLD (es. .gov.it, .it, .com)
                if len(domain_parts) >= 3:
                    tld = ".".join(domain_parts[-2:])
                else:
                    tld = domain_parts[-1] if domain_parts else "org"
                # Conta i domini già visti per consistenza
                domain_key = (EntityType.EMAIL, "domain_" + parts[1])
                if domain_key not in self._mapping:
                    dom_n = self._next_counter("EMAIL_DOMAIN")
                    self._mapping[domain_key] = f"orgdom_{self._format_counter(dom_n)}"
                domain_pseudo = self._mapping[domain_key]
                return f"user_{c}@{domain_pseudo}.{tld}"
            return f"EMAIL_{c}"

        elif entity_type == EntityType.IPV4:
            # Preserva struttura a 4 ottetti con valori fissi
            parts = original_value.split(".")
            if len(parts) == 4:
                # Preserva il primo ottetto (classe di rete) per utilità SOC
                return f"{parts[0]}.{parts[1]}.x.x"
            return f"IPV4_{c}"

        elif entity_type == EntityType.IPV6:
            return f"IPV6_PREFIX_{c}::HOST_{c}"

        elif entity_type == EntityType.URL:
            # Preserva schema e struttura del path
            match = re.match(r"(https?://)([^/]+)(.*)", original_value, re.IGNORECASE)
            if match:
                schema = match.group(1)
                domain = match.group(2)
                path = match.group(3)
                # Pseudonimizza il dominio
                domain_key = (EntityType.HOSTNAME, domain)
                if domain_key not in self._mapping:
                    dom_n = self._next_counter("URL_DOMAIN")
                    self._mapping[domain_key] = f"orgdom_{self._format_counter(dom_n)}"
                domain_pseudo = self._mapping[domain_key]
                # Pseudonimizza il path (mantieni struttura ma sostituisci segmenti)
                path_segments = [s for s in path.split("/") if s]
                pseudo_path = "/".join([f"path_{self._format_counter(i+1)}" for i in range(len(path_segments))])
                return f"{schema}{domain_pseudo}/{pseudo_path}" if pseudo_path else f"{schema}{domain_pseudo}"
            return f"URL_{c}"

        elif entity_type == EntityType.HOSTNAME:
            # Preserva struttura con contatori
            parts = original_value.split(".")
            if len(parts) >= 2:
                tld = parts[-1]
                return f"host_{c}.orgdom_{c}.{tld}"
            return f"HOSTNAME_{c}"

        elif entity_type == EntityType.PHONE:
            # Preserva il prefisso internazionale se presente
            match = re.match(r"(\+\d{1,3}|\d{2,4})", original_value.replace(" ", ""))
            if match and original_value.startswith("+"):
                prefix = match.group(1)
                return f"{prefix} PHONE_{c}"
            return f"PHONE_{c}"

        # Per i tipi senza differenziazione Light/Strict
        return self._generate_strict(entity_type, original_value, c)

    def _generate_strict(self, entity_type: EntityType, original_value: str, c: str) -> str:
        """Genera uno pseudonimo in modalità Strict (massima offuscazione)."""
        type_prefixes = {
            EntityType.EMAIL: "EMAIL",
            EntityType.IPV4: "IPV4",
            EntityType.IPV6: "IPV6",
            EntityType.URL: "URL",
            EntityType.HOSTNAME: "HOSTNAME",
            EntityType.PERSON: "PERSON",
            EntityType.CODICE_FISCALE: "CF",
            EntityType.PARTITA_IVA: "PIVA",
            EntityType.PHONE: "PHONE",
            EntityType.CUSTOM: "CUSTOM",
            EntityType.USERNAME: "USER",
        }
        prefix = type_prefixes.get(entity_type, "ENTITY")
        return f"{prefix}_{c}"

    def process_findings(self, raw_findings: List[RawFinding], file_id: str) -> List[Finding]:
        """
        Converte una lista di RawFinding in Finding con pseudonimi assegnati.
        """
        findings = []
        for raw in raw_findings:
            pseudonym = self.get_or_create_pseudonym(
                raw.entity_type, raw.original_value, raw.canonical_value
            )

            # Costruisci la location
            location = FindingLocation(
                line=raw.source_chunk.line_number,
                sheet_name=raw.source_chunk.sheet_name,
                cell_ref=raw.source_chunk.cell_ref,
                bbox=raw.entity_bbox if raw.entity_bbox else raw.source_chunk.bbox,
                context_snippet=self._get_context(raw),
            )

            finding = Finding(
                file_id=file_id,
                entity_type=raw.entity_type,
                original_value=raw.original_value,
                proposed_pseudonym=pseudonym,
                location=location,
                confidence_score=raw.confidence_score,
                detector_name=raw.detector_name,
            )
            findings.append(finding)

        return findings

    def _get_context(self, raw: RawFinding) -> str:
        """Estrae un breve frammento di contesto attorno al finding."""
        text = raw.source_chunk.text
        start = max(0, raw.start_pos - 30)
        end = min(len(text), raw.end_pos + 30)
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet

    @property
    def mapping(self) -> Dict[str, str]:
        """
        Restituisce la mappa di reversibilità nel formato {pseudonimo: valore_originale}.
        """
        return {
            pseudo: original
            for (_, original), pseudo in self._mapping.items()
            if not original.startswith("domain_")  # Escludi le chiavi interne
        }
