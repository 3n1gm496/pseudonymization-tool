"""
Prometheus metrics per il Local Pseudonymization Tool.

Espone contatori, gauge e istogrammi per il monitoring dell'applicazione.
L'endpoint /api/metrics è gestito da auth_routes.py ed è esentato da auth e CSRF.

Metriche esposte:
  pseudonymizer_scans_total                       — contatore scan completati (label: preset)
  pseudonymizer_applies_total                     — contatore apply completati
  pseudonymizer_errors_total                      — contatore errori HTTP (label: status_code, endpoint)
  pseudonymizer_active_batches                    — gauge batch attivi in memoria
  pseudonymizer_http_requests_total               — contatore richieste HTTP (label: method, endpoint, status)
  pseudonymizer_detector_duration_seconds         — istogramma durata per detector (label: detector_name)
  pseudonymizer_transformation_duration_seconds   — istogramma durata trasformazione per tipo file (label: file_type)
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# ─── Registry dedicato (evita collisioni con metriche di sistema di default) ──
# Usiamo il registry di default per compatibilità con starlette_exporter
# ma registriamo le metriche in modo lazy-safe.

SCANS_TOTAL = Counter(
    "pseudonymizer_scans_total",
    "Numero totale di scansioni completate",
    ["preset"],
)

APPLIES_TOTAL = Counter(
    "pseudonymizer_applies_total",
    "Numero totale di apply completati",
)

ERRORS_TOTAL = Counter(
    "pseudonymizer_errors_total",
    "Numero totale di errori HTTP restituiti",
    ["status_code", "endpoint"],
)

ACTIVE_BATCHES = Gauge(
    "pseudonymizer_active_batches",
    "Numero di batch attivi in memoria",
)

HTTP_REQUESTS_TOTAL = Counter(
    "pseudonymizer_http_requests_total",
    "Numero totale di richieste HTTP ricevute",
    ["method", "endpoint", "status"],
)


DETECTOR_DURATION = Histogram(
    "pseudonymizer_detector_duration_seconds",
    "Durata di esecuzione per singolo detector (label: nome detector)",
    ["detector_name"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

TRANSFORMATION_DURATION = Histogram(
    "pseudonymizer_transformation_duration_seconds",
    "Durata di trasformazione per tipo di file (label: estensione file)",
    ["file_type"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)


def get_metrics_output() -> tuple[bytes, str]:
    """
    Genera l'output Prometheus in formato text/plain 0.0.4.

    Returns:
        (content_bytes, content_type_header)
    """
    return generate_latest(), CONTENT_TYPE_LATEST
