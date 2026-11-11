"""SMTP settings: Gmail-style names, TLS choice, and setups that are refused."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.core.test_provisioning import STRONG_SECRETS

APP_PASSWORD = "abcdefghijklmnop"  # 16 characters, like a Google App Password
GMAIL = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_username": "orders@cliq.example.in",
    "smtp_password": APP_PASSWORD,
    "email_from_address": "orders@cliq.example.in",
}


def make(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_gmail_settings_load_from_the_environment(monkeypatch):
    for name, value in {
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "orders@cliq.example.in",
        "SMTP_PASSWORD": "abcd efgh ijkl mnop",  # as Google displays it
        "SMTP_FROM_EMAIL": "orders@cliq.example.in",
        "SMTP_FROM_NAME": "CliQ",
        "SMTP_USE_TLS": "true",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SMTP_SECURITY", raising=False)
    monkeypatch.delenv("EMAIL_FROM_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_FROM_NAME", raising=False)

    settings = Settings(_env_file=None)

    assert settings.smtp_is_gmail
    assert settings.smtp_security == "starttls"
    assert settings.smtp_password == APP_PASSWORD  # display spaces removed
    assert settings.email_from_address == "orders@cliq.example.in"
    assert settings.email_from_name == "CliQ"
    assert settings.smtp_timeout_seconds == 20
    assert APP_PASSWORD not in repr(settings)  # never printed


def test_the_original_names_still_work():
    settings = make(**GMAIL, email_from_name="CliQ.", smtp_security="starttls")
    assert settings.email_from_name == "CliQ." and settings.smtp_security == "starttls"


@pytest.mark.parametrize(
    ("port", "use_tls", "expected"), [(587, True, "starttls"), (465, True, "ssl"), (25, False, "none")]
)
def test_smtp_use_tls_picks_the_security_mode(port, use_tls, expected):
    settings = make(smtp_host="mail.example.test", smtp_port=port, smtp_use_tls=use_tls,
                    email_from_address="a@mail.example.test")
    assert settings.smtp_security == expected


def test_an_explicit_smtp_security_wins_over_smtp_use_tls():
    settings = make(smtp_host="relay.local", smtp_port=25, smtp_use_tls=True, smtp_security="none",
                    email_from_address="a@relay.example.test")
    assert settings.smtp_security == "none"


def test_without_a_host_nothing_is_required():
    settings = make(smtp_host=None, smtp_username=None, smtp_password=None)
    assert settings.smtp_host is None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"smtp_password": None}, "must be set together"),
        ({"smtp_username": None}, "must be set together"),
        ({"smtp_username": None, "smtp_password": None}, "needs SMTP_USERNAME"),
        ({"smtp_password": "my-normal-google-password"}, "16-character App Password"),
        ({"smtp_security": "none"}, "Gmail SMTP needs TLS"),
        ({"smtp_port": 465}, "Port 465 uses implicit TLS"),
        ({"smtp_security": "ssl"}, "Port 587 uses STARTTLS"),
        ({"email_from_address": "not-an-address"}, "is not an email address"),
        ({"email_from_address": ""}, "is not an email address"),
    ],
)
def test_broken_smtp_settings_are_refused(override, message):
    with pytest.raises(ValidationError, match=message):
        make(**{**GMAIL, **override})


def test_production_needs_a_real_sender_and_encryption():
    production = {"environment": "production", **STRONG_SECRETS}
    assert make(**production, **GMAIL).smtp_is_gmail
    with pytest.raises(ValidationError, match="real sender address"):
        make(**production, **{**GMAIL, "email_from_address": "no-reply@CHANGE_ME.example.com"})
    with pytest.raises(ValidationError, match="unencrypted in production"):
        make(**production, smtp_host="mail.example.net", smtp_port=25, smtp_security="none",
             email_from_address="a@shop.example.net")
