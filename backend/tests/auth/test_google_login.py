"""Google customer login resolves verified identities within the current tenant."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.auth.constants import AuthProvider, UserRole
from app.auth.google import verify_google_credential
from app.core.exceptions import AuthenticationError
from app.users.models import User, UserIdentity


def _install_google_verifier(monkeypatch, *, subject: str, email: str, name: str = "Google User"):
    async def verify(credential: str) -> dict:
        if credential != "valid-google-credential":
            raise AuthenticationError("Invalid Google credential")
        return {
            "sub": subject,
            "email": email,
            "email_verified": True,
            "name": name,
        }

    monkeypatch.setattr("app.auth.service.verify_google_credential", verify)


async def _google_login(client, credential: str = "valid-google-credential"):
    return await client.post(
        "/api/v1/auth/google/login",
        json={"credential": credential},
    )


async def test_new_google_customer_is_created_and_repeat_login_reuses_it(
    client, session, tenant, monkeypatch
):
    _install_google_verifier(
        monkeypatch, subject="google-sub-1", email="google@example.com", name="Google User"
    )

    first = await _google_login(client)
    second = await _google_login(client)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["access_token"]
    assert second.json()["data"]["refresh_token"]

    users = (
        await session.scalars(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == "google@example.com",
            )
        )
    ).all()
    assert len(users) == 1
    assert users[0].phone is None
    assert users[0].name == "Google User"
    assert users[0].role == UserRole.CUSTOMER.value

    identities = (
        await session.scalars(
            select(UserIdentity).where(
                UserIdentity.tenant_id == tenant.id,
                UserIdentity.user_id == users[0].id,
            )
        )
    ).all()
    assert {(identity.provider, identity.subject) for identity in identities} == {
        (AuthProvider.GOOGLE.value, "google-sub-1"),
        (AuthProvider.EMAIL.value, "google@example.com"),
    }


async def test_google_does_not_merge_a_phone_account_by_profile_email(
    client, session, tenant, make_user, monkeypatch
):
    phone_user = await make_user(
        tenant=tenant,
        phone="+919812340001",
        email="shared@example.com",
    )
    _install_google_verifier(
        monkeypatch, subject="google-sub-2", email="shared@example.com"
    )

    response = await _google_login(client)

    assert response.status_code == 200, response.text
    customers = (
        await session.scalars(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == "shared@example.com",
            )
        )
    ).all()
    assert len(customers) == 2
    assert phone_user.id in {customer.id for customer in customers}
    google_user = next(customer for customer in customers if customer.id != phone_user.id)
    assert google_user.phone is None


async def test_google_login_rejects_email_identity_owned_by_another_customer(
    client, session, tenant, make_user, monkeypatch
):
    google_user = await make_user(tenant=tenant, phone=None, email="google@example.com")
    email_owner = await make_user(tenant=tenant, phone=None, email="other@example.com")
    session.add_all(
        [
            UserIdentity(
                tenant_id=tenant.id,
                user_id=google_user.id,
                provider=AuthProvider.GOOGLE.value,
                subject="known-google-sub",
            ),
            UserIdentity(
                tenant_id=tenant.id,
                user_id=email_owner.id,
                provider=AuthProvider.EMAIL.value,
                subject="shared@example.com",
            ),
        ]
    )
    await session.commit()
    _install_google_verifier(
        monkeypatch, subject="known-google-sub", email="shared@example.com"
    )

    response = await _google_login(client)

    assert response.status_code == 401


async def test_google_identity_is_scoped_to_tenant(
    client, other_client, session, tenant, other_tenant, monkeypatch
):
    _install_google_verifier(
        monkeypatch, subject="shared-google-sub", email="tenant@example.com"
    )

    zeen_response = await _google_login(client)
    other_response = await _google_login(other_client)

    assert zeen_response.status_code == 200, zeen_response.text
    assert other_response.status_code == 200, other_response.text
    rows = (
        await session.scalars(
            select(UserIdentity).where(
                UserIdentity.provider == AuthProvider.GOOGLE.value,
                UserIdentity.subject == "shared-google-sub",
            )
        )
    ).all()
    assert {identity.tenant_id for identity in rows} == {tenant.id, other_tenant.id}
    assert len({identity.user_id for identity in rows}) == 2


async def test_invalid_google_credential_is_rejected(client, tenant, monkeypatch):
    _install_google_verifier(
        monkeypatch, subject="google-sub-invalid", email="invalid@example.com"
    )

    response = await _google_login(client, credential="invalid")

    assert response.status_code == 401


async def test_google_verifier_uses_configured_audience(monkeypatch):
    expected_audience = "zeen-web-client-id"
    monkeypatch.setattr(
        "app.auth.google.get_settings",
        lambda: SimpleNamespace(google_client_id=expected_audience),
    )

    def verify(token, request, audience):
        assert token == "signed-id-token"
        assert audience == expected_audience
        return {
            "iss": "https://accounts.google.com",
            "sub": "stable-google-sub",
            "email": "customer@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", verify)

    claims = await verify_google_credential("signed-id-token")

    assert claims["sub"] == "stable-google-sub"


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.example", "sub": "sub", "email": "a@b.com", "email_verified": True},
        {"iss": "accounts.google.com", "sub": "sub", "email": "a@b.com", "email_verified": False},
        {"iss": "accounts.google.com", "sub": "", "email": "a@b.com", "email_verified": True},
        {"iss": "accounts.google.com", "sub": "sub", "email": "", "email_verified": True},
    ],
)
async def test_google_verifier_rejects_untrusted_or_incomplete_claims(monkeypatch, claims):
    monkeypatch.setattr(
        "app.auth.google.get_settings",
        lambda: SimpleNamespace(google_client_id="zeen-web-client-id"),
    )
    monkeypatch.setattr(
        "app.auth.google.id_token.verify_oauth2_token",
        lambda token, request, audience: claims,
    )

    with pytest.raises(AuthenticationError):
        await verify_google_credential("signed-id-token")


async def test_google_verifier_maps_google_signature_or_expiry_failure(monkeypatch):
    monkeypatch.setattr(
        "app.auth.google.get_settings",
        lambda: SimpleNamespace(google_client_id="zeen-web-client-id"),
    )

    def reject_token(token, request, audience):
        raise ValueError("invalid token")

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", reject_token)

    with pytest.raises(AuthenticationError, match="Invalid Google credential"):
        await verify_google_credential("invalid-token")
