"""No public route creates accounts, and the app refuses an environment it does not know."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import KNOWN_ENVIRONMENTS, Settings, get_settings
from app.users.models import User

PROVISIONING_ROUTES = ("/api/v1/users/admin", "/api/v1/users/staff", "/api/v1/users/customer")

PAYLOAD = {
    "email": "intruder@example.com",
    "phone": "+919800000999",
    "name": "Intruder",
    "password": "a-long-enough-password",
}

STRONG_SECRETS = {
    "jwt_secret": "a" * 40,
    "jwt_refresh_secret": "b" * 40,
    # A valid Fernet key (32 url-safe base64 bytes); production requires one.
    "secrets_encryption_key": "dGVzdC1vbmx5LWZlcm5ldC1rZXktMzItYnl0ZXMhISE=",
}


@pytest.mark.parametrize("environment", sorted(KNOWN_ENVIRONMENTS))
@pytest.mark.parametrize("path", PROVISIONING_ROUTES)
async def test_no_environment_exposes_account_provisioning(
    client, session, tenant, monkeypatch, environment, path
):
    monkeypatch.setattr(get_settings(), "environment", environment)

    response = await client.post(path, json=PAYLOAD)

    assert response.status_code == 404
    created = await session.scalar(select(func.count()).select_from(User))
    assert created == 0


@pytest.mark.parametrize("environment", ["", "prodution", "live", "dev", "PRODUCTION-EU"])
def test_an_unknown_environment_refuses_to_start(environment):
    with pytest.raises(ValidationError, match="Unknown ENVIRONMENT"):
        Settings(environment=environment, **STRONG_SECRETS)


@pytest.mark.parametrize("environment", sorted(KNOWN_ENVIRONMENTS | {"Production", "STAGING"}))
def test_every_known_environment_starts(environment):
    assert Settings(environment=environment, **STRONG_SECRETS).environment == environment


def test_production_needs_a_secrets_encryption_key():
    weak = {k: v for k, v in STRONG_SECRETS.items() if k != "secrets_encryption_key"}
    with pytest.raises(ValidationError, match="SECRETS_ENCRYPTION_KEY is required"):
        Settings(environment="production", **weak)
    with pytest.raises(ValidationError, match="must be a Fernet key"):
        Settings(environment="production", **{**weak, "secrets_encryption_key": "CHANGE_ME"})
