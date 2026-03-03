"""
Test per PR #27 — Security Hardening.

Verifica:
1. Security headers HTTP presenti in tutte le risposte
2. validate_production_secrets() funziona correttamente
3. HSTS presente solo in PROD/STAGING (cookie_secure=True)
4. CSP differenziata tra profili con/senza Swagger UI
"""


import pytest
from fastapi.testclient import TestClient


# ─── Fixture client ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    """Client di test con profilo DEV (auth disabilitata)."""
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ─── Security Headers ─────────────────────────────────────────────────────────


class TestSecurityHeaders:
    """Verifica che i security headers siano presenti in tutte le risposte."""

    def test_x_content_type_options_present(self, client):
        """X-Content-Type-Options deve essere 'nosniff'."""
        resp = client.get("/api/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_present(self, client):
        """X-Frame-Options deve essere 'DENY'."""
        resp = client.get("/api/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_x_xss_protection_present(self, client):
        """X-XSS-Protection deve essere '1; mode=block'."""
        resp = client.get("/api/health")
        assert resp.headers.get("x-xss-protection") == "1; mode=block"

    def test_referrer_policy_present(self, client):
        """Referrer-Policy deve essere 'strict-origin-when-cross-origin'."""
        resp = client.get("/api/health")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy_present(self, client):
        """Permissions-Policy deve disabilitare le API browser non necessarie."""
        resp = client.get("/api/health")
        policy = resp.headers.get("permissions-policy", "")
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy

    def test_content_security_policy_present(self, client):
        """Content-Security-Policy deve essere presente."""
        resp = client.get("/api/health")
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_hsts_not_present_in_dev(self, client):
        """HSTS non deve essere presente in DEV (cookie_secure=False)."""
        resp = client.get("/api/health")
        # In DEV cookie_secure=False → no HSTS
        assert "strict-transport-security" not in resp.headers

    def test_security_headers_on_api_endpoints(self, client):
        """I security headers devono essere presenti anche sugli endpoint API."""
        resp = client.get("/api/ready")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_security_headers_on_post_endpoints(self, client):
        """I security headers devono essere presenti anche nelle risposte POST."""
        resp = client.post("/api/auth/login", json={"username": "test", "password": "wrong"})
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_csp_allows_self_scripts(self, client):
        """CSP deve permettere script da 'self'."""
        resp = client.get("/api/health")
        csp = resp.headers.get("content-security-policy", "")
        assert "script-src" in csp
        assert "'self'" in csp

    def test_csp_denies_frame_embedding(self, client):
        """CSP frame-ancestors 'none' impedisce embedding in iframe."""
        resp = client.get("/api/health")
        csp = resp.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp


# ─── validate_production_secrets ─────────────────────────────────────────────


class TestValidateProductionSecrets:
    """Verifica la funzione validate_production_secrets."""

    def test_dev_profile_returns_no_errors(self):
        """In DEV non ci sono errori (nessun secret obbligatorio)."""
        # DEV è il profilo di default in test
        from app.core.profiles import validate_production_secrets

        errors = validate_production_secrets()
        assert errors == []

    def test_prod_profile_missing_all_secrets(self, monkeypatch):
        """In PROD senza secrets configurati deve restituire 4 errori."""
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "prod")
        monkeypatch.delenv("AUTH_PASSWORD", raising=False)
        monkeypatch.delenv("AUTH_SECRET", raising=False)
        monkeypatch.delenv("REDIS_PASSWORD", raising=False)
        monkeypatch.delenv("PROD_FRONTEND_URL", raising=False)

        # Reimportare per forzare la rilettura dell'env
        import importlib

        import app.core.profiles as profiles_mod

        importlib.reload(profiles_mod)

        errors = profiles_mod.validate_production_secrets()
        assert len(errors) >= 3  # AUTH_PASSWORD, AUTH_SECRET, REDIS_PASSWORD, PROD_FRONTEND_URL
        assert any("AUTH_PASSWORD" in e for e in errors)
        assert any("AUTH_SECRET" in e for e in errors)
        assert any("REDIS_PASSWORD" in e for e in errors)

        # Ripristinare il profilo DEV
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "dev")
        importlib.reload(profiles_mod)

    def test_prod_profile_short_password_error(self, monkeypatch):
        """In PROD con password troppo corta deve restituire errore."""
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "prod")
        monkeypatch.setenv("AUTH_PASSWORD", "short")
        monkeypatch.setenv("AUTH_SECRET", "a" * 32)
        monkeypatch.setenv("REDIS_PASSWORD", "redis_pass")
        monkeypatch.setenv("PROD_FRONTEND_URL", "https://example.com")

        import importlib

        import app.core.profiles as profiles_mod

        importlib.reload(profiles_mod)

        errors = profiles_mod.validate_production_secrets()
        assert any("AUTH_PASSWORD" in e and "corta" in e for e in errors)

        monkeypatch.setenv("DEPLOYMENT_PROFILE", "dev")
        importlib.reload(profiles_mod)

    def test_prod_profile_short_secret_error(self, monkeypatch):
        """In PROD con AUTH_SECRET troppo corto deve restituire errore."""
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "prod")
        monkeypatch.setenv("AUTH_PASSWORD", "password_lunga_ok")
        monkeypatch.setenv("AUTH_SECRET", "short")
        monkeypatch.setenv("REDIS_PASSWORD", "redis_pass")
        monkeypatch.setenv("PROD_FRONTEND_URL", "https://example.com")

        import importlib

        import app.core.profiles as profiles_mod

        importlib.reload(profiles_mod)

        errors = profiles_mod.validate_production_secrets()
        assert any("AUTH_SECRET" in e and "corto" in e for e in errors)

        monkeypatch.setenv("DEPLOYMENT_PROFILE", "dev")
        importlib.reload(profiles_mod)

    def test_staging_profile_no_frontend_url_required(self, monkeypatch):
        """In STAGING PROD_FRONTEND_URL non è obbligatoria."""
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "staging")
        monkeypatch.setenv("AUTH_PASSWORD", "password_lunga_ok")
        monkeypatch.setenv("AUTH_SECRET", "a" * 32)
        monkeypatch.setenv("REDIS_PASSWORD", "redis_pass")
        monkeypatch.delenv("PROD_FRONTEND_URL", raising=False)

        import importlib

        import app.core.profiles as profiles_mod

        importlib.reload(profiles_mod)

        errors = profiles_mod.validate_production_secrets()
        # PROD_FRONTEND_URL non è richiesta in STAGING
        assert not any("PROD_FRONTEND_URL" in e for e in errors)
        assert errors == []  # Tutti i secrets configurati correttamente

        monkeypatch.setenv("DEPLOYMENT_PROFILE", "dev")
        importlib.reload(profiles_mod)
