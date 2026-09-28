import pytest

from voxlibera.config import (
    Settings,
    StartupSecurityDecision,
    StartupSecurityError,
    env_flag_is_set,
    evaluate_startup_security,
)


def test_loopback_host_without_key_is_allowed():
    for host in ("127.0.0.1", "localhost", "::1"):
        assert evaluate_startup_security(host, None, allow_open=False) is StartupSecurityDecision.SECURE


def test_non_loopback_host_without_key_is_refused():
    with pytest.raises(StartupSecurityError):
        evaluate_startup_security("0.0.0.0", None, allow_open=False)


def test_non_loopback_host_with_key_is_allowed():
    decision = evaluate_startup_security("0.0.0.0", "secret", allow_open=False)
    assert decision is StartupSecurityDecision.SECURE


def test_allow_open_escape_hatch_permits_open_network_startup():
    decision = evaluate_startup_security("0.0.0.0", None, allow_open=True)
    assert decision is StartupSecurityDecision.OPEN_ALLOWED


def test_empty_string_admin_key_is_treated_as_unset():
    # compose.yaml passes VOXLIBERA_ADMIN_KEY="" when the operator did not set one; that must not
    # be mistaken for "a key is configured".
    with pytest.raises(StartupSecurityError):
        evaluate_startup_security("0.0.0.0", "", allow_open=False)


def test_settings_from_environment_treats_empty_string_admin_key_as_unset(monkeypatch):
    monkeypatch.setenv("VOXLIBERA_ADMIN_KEY", "")
    monkeypatch.delenv("VOXLIBERA_INGEST_TOKEN", raising=False)
    settings = Settings.from_environment()
    assert settings.admin_key is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("0", False),
        ("false", False),
        ("False", False),
        ("no", False),
        ("1", True),
        ("true", True),
        ("yes", True),
    ],
)
def test_env_flag_is_set(value, expected):
    assert env_flag_is_set(value) is expected
