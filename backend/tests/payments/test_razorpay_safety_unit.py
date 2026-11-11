"""Gateway checks that run without the database-backed pytest fixture."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from app.core.exceptions import ServiceUnavailableError
from app.payments import razorpay


class RazorpayFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_uses_server_credentials_and_returns_gateway_record(self):
        requests = []

        def answer(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"id": "pay_test", "status": "captured"})

        client_factory = httpx.AsyncClient
        with (
            patch.object(razorpay, "credentials", return_value=razorpay.Credentials("key", "secret", "https://gateway.invalid/v1", 5.0)),
            patch.object(razorpay.httpx, "AsyncClient", side_effect=lambda **kwargs: client_factory(transport=httpx.MockTransport(answer), **kwargs)),
        ):
            result = await razorpay.fetch_payment("pay_test")

        self.assertEqual(result["status"], "captured")
        self.assertEqual(requests[0].url.path, "/v1/payments/pay_test")
        self.assertTrue(requests[0].headers["authorization"].startswith("Basic "))

    async def test_gateway_error_does_not_return_a_payment(self):
        client_factory = httpx.AsyncClient
        with (
            patch.object(razorpay, "credentials", return_value=razorpay.Credentials("key", "secret", "https://gateway.invalid/v1", 5.0)),
            patch.object(razorpay.httpx, "AsyncClient", side_effect=lambda **kwargs: client_factory(transport=httpx.MockTransport(lambda request: httpx.Response(503)), **kwargs)),
            self.assertRaises(ServiceUnavailableError),
        ):
            await razorpay.fetch_payment("pay_test")


if __name__ == "__main__":
    unittest.main()
