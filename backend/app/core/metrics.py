"""
Prometheus metrics per il Local Pseudonymization Tool.

Espone contatori e gauge standard per il monitoring dell'applicazione.
L'endpoint /api/metrics è gestito da auth_routes.py ed è esentato da auth e CSRF.

Metriche esposte:
  pseudonymizer_scans_total          — contatore scan completati (label: preset)
  pseudonymizer_applies_total        — contatore apply completati
  pseudonymizer_errors_total         — contatore errori HTTP (label: status_code, endpoint)
  pseudonymizer_active_batches       — gauge batch attivi in memoria
  pseudonymizer_http_requests_total  — contatore richieste HTTP (label: method, endpoint, status)
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

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


def get_metrics_output() -> tuple[bytes, str]:
    """
    Genera l'output Prometheus in formato text/plain 0.0.4.

    Returns:
        (content_bytes, content_type_header)
    """
    return generate_latest(), CONTENT_TYPE_LATEST
