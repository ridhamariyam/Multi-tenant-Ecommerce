"""MSG91 widget verification, against a mocked provider rather than the network."""

from __future__ import annotations

import httpx
import pytest

from app.auth import widget
from app.core.exceptions import AuthenticationError, ServiceUnavailableError

VERIFIED_PHONE = "+919812345678"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """A key is present unless a test deliberately removes it."""
    monkeypatch.setattr(widget.get_settings(), "msg91_auth_key", "test-authkey")


@pytest.fixture
def msg91_replies(monkeypatch):
    """Answer MSG91's verify endpoint with a canned response."""
    sent: list[httpx.Request] = []

    def install(handler):
        real_init = httpx.AsyncClient.__init__

        def init(self, *args, **kwargs):
            def record(request: httpx.Request) -> httpx.Response:
                sent.append(request)
                return handler(request)

            kwargs["transport"] = httpx.MockTransport(record)
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
        return sent

    return install


def replies(body: dict | None, status_code: int = 200):
    def handler(_request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status_code, text="not json")
        return httpx.Response(status_code, json=body)

    return handler


async def test_a_verified_token_yields_the_number_msg91_attests_to(msg91_replies):
    sent = msg91_replies(replies({"type": "success", "message": "919812345678"}))

    assert await widget.verify_access_token("tok") == VERIFIED_PHONE

    request = sent[-1]
    assert str(request.url) == widget.get_settings().msg91_widget_verify_url
    assert b'"access-token"' in request.content
    # The account key authenticates us to MSG91 and must never be the widget
    # token the browser holds.
    assert b'"authkey"' in request.content


async def test_the_number_is_normalised_to_e164(msg91_replies):
    msg91_replies(replies({"type": "success", "message": "9812345678"}))

    assert await widget.verify_access_token("tok") == VERIFIED_PHONE


async def test_a_rejected_token_is_an_authentication_failure(msg91_replies):
    msg91_replies(replies({"type": "error", "message": "Invalid access token"}))

    with pytest.raises(AuthenticationError):
        await widget.verify_access_token("forged")


async def test_a_200_carrying_an_error_is_still_refused(msg91_replies):
    """MSG91 reports a bad token in the body while answering 200."""
    msg91_replies(replies({"type": "error", "message": "expired"}, status_code=200))

    with pytest.raises(AuthenticationError):
        await widget.verify_access_token("expired")


async def test_success_without_a_usable_number_is_refused(msg91_replies):
    """Verified, but MSG91 did not say who for -- we must not guess."""
    msg91_replies(replies({"type": "success", "message": "Token verified"}))

    with pytest.raises(AuthenticationError):
        await widget.verify_access_token("tok")


async def test_a_non_json_body_is_refused(msg91_replies):
    msg91_replies(replies(None))

    with pytest.raises(AuthenticationError):
        await widget.verify_access_token("tok")


async def test_an_unreachable_provider_is_not_reported_as_a_bad_code(msg91_replies):
    def explode(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    msg91_replies(explode)

    with pytest.raises(ServiceUnavailableError):
        await widget.verify_access_token("tok")


async def test_verification_is_refused_when_no_auth_key_is_configured(monkeypatch):
    settings = widget.get_settings()
    monkeypatch.setattr(settings, "msg91_auth_key", None)

    with pytest.raises(ServiceUnavailableError):
        await widget.verify_access_token("tok")


async def test_a_number_returned_as_json_int_is_accepted(msg91_replies):
    """JSON has one number type; an unquoted mobile is still the identifier."""
    msg91_replies(replies({"type": "success", "message": 919812345678}))

    assert await widget.verify_access_token("tok") == VERIFIED_PHONE


async def test_a_nested_identifier_is_found(msg91_replies):
    msg91_replies(
        replies({"type": "success", "data": {"mobile": "919812345678"}, "message": "ok"})
    )

    assert await widget.verify_access_token("tok") == VERIFIED_PHONE


async def test_a_timestamp_is_not_mistaken_for_a_number(msg91_replies):
    """A ten-digit epoch normalises to valid-looking E.164 -- it must not be read
    as an identity just because it parses."""
    msg91_replies(replies({"type": "success", "message": "ok", "createdAt": 1757330000}))

    with pytest.raises(AuthenticationError):
        await widget.verify_access_token("tok")


async def test_a_provider_server_error_is_not_a_bad_code(msg91_replies):
    msg91_replies(replies({"type": "error"}, status_code=502))

    with pytest.raises(ServiceUnavailableError):
        await widget.verify_access_token("tok")


async def test_being_throttled_by_msg91_is_not_a_bad_code(msg91_replies):
    msg91_replies(replies({"type": "error", "message": "too many"}, status_code=429))

    with pytest.raises(ServiceUnavailableError):
        await widget.verify_access_token("tok")


async def test_a_boolean_is_never_read_as_a_number(msg91_replies):
    msg91_replies(replies({"type": "success", "message": True}))

    with pytest.raises(AuthenticationError):
        await widget.verify_access_token("tok")


async def test_an_unwhitelisted_ip_is_not_reported_as_a_bad_code(msg91_replies):
    """MSG91's 418: the auth key is fine, this server's IP is not whitelisted."""
    msg91_replies(
        replies({"message": "AuthenticationFailure", "type": "error", "code": "418"})
    )

    with pytest.raises(ServiceUnavailableError):
        await widget.verify_access_token("a-perfectly-good-token")


async def test_a_rejected_auth_key_is_not_reported_as_a_bad_code(msg91_replies):
    msg91_replies(
        replies({"message": "AuthenticationFailure", "type": "error", "code": "201"})
    )

    with pytest.raises(ServiceUnavailableError):
        await widget.verify_access_token("a-perfectly-good-token")


async def test_a_genuinely_bad_token_is_still_a_401(msg91_replies):
    """Codes that are not ours to fix must stay an authentication failure."""
    msg91_replies(replies({"message": "Invalid token", "type": "error", "code": "500"}))

    with pytest.raises(AuthenticationError):
        await widget.verify_access_token("forged")
