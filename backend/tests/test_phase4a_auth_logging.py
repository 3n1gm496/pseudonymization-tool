import os
from types import SimpleNamespace

from app.core import auth, logging_config


def test_auth_b64_roundtrip():
    raw = "session:admin:12345"
    enc = auth._b64(raw)
    dec = auth._b64_decode(enc)
    assert dec == raw


def test_verify_credentials_when_auth_disabled():
    old = auth.AUTH_ENABLED
    try:
        auth.AUTH_ENABLED = False
        assert auth.verify_credentials("any", "any") is True
    finally:
        auth.AUTH_ENABLED = old


def test_verify_credentials_when_auth_enabled():
    old_enabled = auth.AUTH_ENABLED
    old_user = auth.ADMIN_USERNAME
    old_pwd = auth._password_env
    try:
        auth.AUTH_ENABLED = True
        auth.ADMIN_USERNAME = "admin"
        auth._password_env = "secret"

        assert auth.verify_credentials("admin", "secret") is True
        assert auth.verify_credentials("admin", "wrong") is False
        assert auth.verify_credentials("wrong", "secret") is False
    finally:
        auth.AUTH_ENABLED = old_enabled
        auth.ADMIN_USERNAME = old_user
        auth._password_env = old_pwd


def test_create_validate_and_destroy_session():
    old_enabled = auth.AUTH_ENABLED
    auth.AUTH_ENABLED = True
    auth._sessions.clear()
    try:
        token, _expires, _ = auth.create_session("admin")
        assert auth.validate_session(token) == "admin"

        auth.destroy_session(token)
        assert auth.validate_session(token) is None
    finally:
        auth.AUTH_ENABLED = old_enabled
        auth._sessions.clear()


def test_validate_session_invalid_signature_and_format():
    old_enabled = auth.AUTH_ENABLED
    auth.AUTH_ENABLED = True
    try:
        assert auth.validate_session(None) is None
        assert auth.validate_session("invalid-token") is None

        token, _, _ = auth.create_session("admin")
        payload, sig = token.split(".", 1)
        tampered = f"{payload}.{sig[::-1]}"
        assert auth.validate_session(tampered) is None
    finally:
        auth.AUTH_ENABLED = old_enabled
        auth._sessions.clear()


def test_extract_token_from_request_cookie_and_bearer():
    req_cookie = SimpleNamespace(
        cookies={auth.SESSION_COOKIE_NAME: "cookie-token"},
        headers={},
    )
    assert auth.extract_token_from_request(req_cookie) == "cookie-token"

    req_bearer = SimpleNamespace(
        cookies={},
        headers={"Authorization": "Bearer header-token"},
    )
    assert auth.extract_token_from_request(req_bearer) == "header-token"

    req_none = SimpleNamespace(cookies={}, headers={})
    assert auth.extract_token_from_request(req_none) is None


def test_add_app_context_enriches_event_dict():
    event = {"event": "hello"}
    out = logging_config.add_app_context(None, "info", event)
    assert out["app"] == "pseudonymization-tool"
    assert out["version"] == "5.0.0"


def test_configure_logging_json_and_console():
    logging_config.configure_logging(log_level="INFO", json_logs=False)
    logging_config.configure_logging(log_level="WARNING", json_logs=True)
    logger = logging_config.get_logger("test.logger")
    assert logger is not None


def test_request_and_error_logging_helpers(mocker):
    fake_logger = mocker.Mock()
    mocker.patch("app.core.logging_config.get_logger", return_value=fake_logger)

    logging_config.log_request_start("GET", "/health", "req-1", user="admin")
    logging_config.log_request_end("GET", "/health", "req-1", 200, 12.3456)
    logging_config.log_error("ValueError", "boom", request_id="req-1")

    assert fake_logger.info.call_count == 2
    assert fake_logger.error.call_count == 1


def test_env_flag_parsing_defaults_and_values(monkeypatch):
    monkeypatch.delenv("AUTH_SESSION_COOKIE_SECURE", raising=False)
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=True) is True
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=False) is False

    monkeypatch.setenv("AUTH_SESSION_COOKIE_SECURE", "true")
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=False) is True
    monkeypatch.setenv("AUTH_SESSION_COOKIE_SECURE", "1")
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=False) is True
    monkeypatch.setenv("AUTH_SESSION_COOKIE_SECURE", "yes")
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=False) is True
    monkeypatch.setenv("AUTH_SESSION_COOKIE_SECURE", "on")
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=False) is True

    monkeypatch.setenv("AUTH_SESSION_COOKIE_SECURE", "false")
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=True) is False
    monkeypatch.setenv("AUTH_SESSION_COOKIE_SECURE", "0")
    assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=True) is False


def test_session_cookie_secure_default_enabled(monkeypatch):
    monkeypatch.delenv("AUTH_SESSION_COOKIE_SECURE", raising=False)
    old = os.environ.get("AUTH_SESSION_COOKIE_SECURE")
    try:
        assert auth._env_flag("AUTH_SESSION_COOKIE_SECURE", default=True) is True
    finally:
        if old is None:
            os.environ.pop("AUTH_SESSION_COOKIE_SECURE", None)
        else:
            os.environ["AUTH_SESSION_COOKIE_SECURE"] = old
