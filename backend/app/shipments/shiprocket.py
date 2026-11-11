"""Server-side Shiprocket API client.

Endpoints, fields and responses follow the official documentation at
https://apidocs.shiprocket.in/ (Postman collection "Shiprocket API"). The
password never leaves the backend; the bearer token is cached in Redis for
less than its documented 10-day validity and renewed once on a 401.

Retries: reads (tracking, rates, lookups) are retried on 429, 5xx and
timeouts. Calls that book or change something are sent once; a timeout or
server error on them is reported as *ambiguous* so the caller reconciles
(looks the result up) instead of booking twice.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import httpx

from app.core import cache
from app.core.config import get_settings
from app.shipments.constants import TOKEN_CACHE_PREFIX
from app.shipments.provider import (
    AwbAssignment,
    BookedOrder,
    BookingRequest,
    CourierRate,
    PickupLocation,
    PickupResult,
    ProviderNotConfiguredError,
    RateQuery,
    ShippingProviderError,
    TrackingScan,
    TrackingUpdate,
)

logger = logging.getLogger(__name__)

# Shiprocket reports times in India time without an offset.
IST = timezone(timedelta(hours=5, minutes=30))
MAX_BACKOFF_SECONDS = 8.0
UNREACHABLE = "Shiprocket could not be reached"


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str
    api_url: str
    timeout_seconds: float
    token_ttl_seconds: int
    read_retries: int


def is_configured(tenant_id: UUID | None = None) -> bool:
    try:
        credentials(tenant_id)
    except ProviderNotConfiguredError:
        return False
    return True


def credentials(tenant_id: UUID | None = None) -> Credentials:
    """Resolve server-held credentials for this tenant, never from a request body."""
    settings = get_settings()
    mapped = settings.shiprocket_tenant_credentials.get(tenant_id, {})
    bound = tenant_id is not None and str(tenant_id) == settings.shiprocket_tenant_id
    email = mapped.get("email") or (settings.shiprocket_email if bound else None)
    password = mapped.get("password") or (settings.shiprocket_password if bound else None)
    if not email or not password:
        raise ProviderNotConfiguredError(
            "Shiprocket credentials are not configured for this store. Configure the "
            "server's SHIPROCKET_TENANT_ID and API credentials, or its tenant credentials map."
        )
    return Credentials(
        email=email,
        password=password,
        api_url=settings.shiprocket_api_url.rstrip("/"),
        timeout_seconds=settings.shiprocket_timeout_seconds,
        token_ttl_seconds=settings.shiprocket_token_ttl_seconds,
        read_retries=max(0, settings.shiprocket_read_retries),
    )


# ------------------------------------------------------------------ parsing


def parse_time(value: Any) -> datetime | None:
    """Shiprocket's timestamps: "2022-07-19 11:37:00" or, in webhooks, "23 05 2023 11:43:52"."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d %m %Y %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, pattern)
        except ValueError:
            continue
        return parsed.replace(tzinfo=IST)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def _text(value: Any, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "NA":
        return None
    return text[:limit] if limit else text


def _id(value: Any) -> str | None:
    """A provider id as text; 0/""/None mean none was given."""
    if value in (None, "", 0, "0"):
        return None
    return str(value)


def _error_message(payload: Any, fallback: str) -> str:
    if not isinstance(payload, dict):
        return fallback
    message = _text(payload.get("message")) or fallback
    errors = payload.get("errors")
    if isinstance(errors, dict) and errors:
        parts = []
        for name, problems in errors.items():
            text = "; ".join(str(p) for p in problems) if isinstance(problems, list) else problems
            parts.append(f"{name}: {text}")
        message = f"{message} ({' | '.join(parts)})"
    return message[:480]


def scan_from(entry: dict[str, Any]) -> TrackingScan | None:
    occurred = parse_time(entry.get("date"))
    if occurred is None:
        return None
    return TrackingScan(
        occurred_at=occurred,
        status_code=_int(entry.get("sr-status")),
        status_label=_text(entry.get("sr-status-label"), 100),
        courier_status=_text(entry.get("status"), 50),
        activity=_text(entry.get("activity"), 500),
        location=_text(entry.get("location"), 150),
        raw=entry,
    )


def parse_webhook(payload: dict[str, Any]) -> TrackingUpdate:
    """A tracking webhook body, as in the documentation's sample."""
    scans = [
        scan
        for entry in payload.get("scans") or []
        if isinstance(entry, dict) and (scan := scan_from(entry)) is not None
    ]
    return TrackingUpdate(
        awb_code=_text(payload.get("awb"), 64),
        # shipment_status_id is the documented shipment status code; the
        # sample's current_status_id uses a different numbering.
        status_code=_int(payload.get("shipment_status_id")),
        status_label=_text(payload.get("shipment_status") or payload.get("current_status"), 100),
        occurred_at=parse_time(payload.get("current_timestamp")),
        etd=_text(payload.get("etd"), 40),
        track_url=None,
        courier_name=_text(payload.get("courier_name"), 100),
        scans=scans,
        raw=payload,
    )


def _phone(value: str) -> str:
    """Shiprocket wants the 10-digit Indian number, without +91."""
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-10:] if len(digits) > 10 else digits


def _number(value: Decimal) -> float:
    return float(value)


def booking_payload(booking: BookingRequest) -> dict[str, Any]:
    first, _, last = booking.customer_name.strip().partition(" ")
    return {
        "order_id": booking.channel_order_id,
        "order_date": booking.order_date.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
        "pickup_location": booking.pickup_location,
        "billing_customer_name": first,
        "billing_last_name": last.strip(),
        "billing_address": booking.address_line_1,
        "billing_address_2": booking.address_line_2 or "",
        "billing_city": booking.city[:30],
        "billing_pincode": booking.postcode,
        "billing_state": booking.state,
        "billing_country": booking.country,
        "billing_email": booking.email or "",
        "billing_phone": _phone(booking.phone),
        "shipping_is_billing": True,
        "order_items": [
            {
                "name": item.name,
                "sku": item.sku,
                "units": item.units,
                "selling_price": _number(item.selling_price),
                "discount": _number(item.discount),
                **({"tax": _number(item.tax_rate)} if item.tax_rate is not None else {}),
                **({"hsn": item.hsn} if item.hsn else {}),
            }
            for item in booking.items
        ],
        "payment_method": "COD" if booking.cod else "Prepaid",
        "shipping_charges": _number(booking.shipping_charges),
        "transaction_charges": _number(booking.transaction_charges),
        "total_discount": _number(booking.total_discount),
        "sub_total": _number(booking.sub_total),
        "length": _number(booking.package.length_cm),
        "breadth": _number(booking.package.breadth_cm),
        "height": _number(booking.package.height_cm),
        "weight": _number(booking.package.weight_kg),
    }


def _booked(order: dict[str, Any]) -> BookedOrder | None:
    provider_order_id = _id(order.get("id"))
    if provider_order_id is None:
        return None
    shipments = order.get("shipments")
    shipment = (
        (shipments[0] if isinstance(shipments, list) and shipments else shipments)
        if shipments
        else None
    )
    shipment = shipment if isinstance(shipment, dict) else {}
    return BookedOrder(
        provider_order_id=provider_order_id,
        provider_shipment_id=_id(shipment.get("id")),
        awb_code=_text(shipment.get("awb"), 64),
        courier_id=_id(shipment.get("courier_id")),
        courier_name=_text(shipment.get("courier"), 100),
        status=_text(order.get("status"), 50),
    )


# ------------------------------------------------------------------- client


class ShiprocketClient:
    """Implements `ShippingProviderClient` against apiv2.shiprocket.in."""

    def __init__(
        self,
        creds: Credentials | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep=asyncio.sleep,
    ) -> None:
        self.creds = creds or credentials()
        self._transport = transport
        self._sleep = sleep
        self._token: str | None = None
        self._token_expires_at = 0.0

    # ------------------------------------------------------------ auth

    @property
    def _cache_key(self) -> str:
        fingerprint = hashlib.sha256(
            f"{self.creds.api_url}|{self.creds.email}|{self.creds.password}".encode()
        ).hexdigest()[:32]
        return f"{TOKEN_CACHE_PREFIX}:{fingerprint}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.creds.api_url,
            timeout=self.creds.timeout_seconds,
            transport=self._transport,
        )

    async def _cached_token(self) -> str | None:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        self._token = None
        try:
            # Redis owns the remaining lifetime; do not extend it in memory.
            return await cache.get_redis().get(self._cache_key)
        except Exception:  # Redis down: fall back to logging in
            logger.warning("Shiprocket token cache unavailable")
        return None

    async def _forget_token(self) -> None:
        self._token = None
        try:
            await cache.get_redis().delete(self._cache_key)
        except Exception:
            logger.warning("Shiprocket token cache unavailable")

    async def _login(self, client: httpx.AsyncClient) -> str:
        try:
            response = await client.post(
                "/auth/login",
                json={"email": self.creds.email, "password": self.creds.password},
            )
        except httpx.HTTPError as exc:
            raise ShippingProviderError(UNREACHABLE, retryable=True) from exc
        payload = _json(response)
        token = payload.get("token") if isinstance(payload, dict) else None
        if response.status_code != httpx.codes.OK or not isinstance(token, str) or not token:
            raise ShippingProviderError(
                "Shiprocket rejected the API user's login. Check SHIPROCKET_EMAIL and "
                "SHIPROCKET_PASSWORD (an API user, not the panel login).",
                status_code=response.status_code,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        self._token = token
        self._token_expires_at = time.monotonic() + self.creds.token_ttl_seconds
        try:
            await cache.get_redis().set(self._cache_key, token, ex=self.creds.token_ttl_seconds)
        except Exception:
            logger.warning("Shiprocket token cache unavailable")
        return token

    # --------------------------------------------------------- transport

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotent: bool,
        accept: tuple[int, ...] = (200, 202, 204),
    ) -> Any:
        attempts = 1 + (self.creds.read_retries if idempotent else 0)
        relogged = False
        attempt = 0
        async with self._client() as client:
            while True:
                attempt += 1
                token = await self._cached_token() or await self._login(client)
                try:
                    response = await client.request(
                        method,
                        path,
                        json=json,
                        params=params,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    # The request never reached Shiprocket.
                    if attempt < attempts:
                        await self._backoff(attempt)
                        continue
                    raise ShippingProviderError(UNREACHABLE, retryable=True) from exc
                except httpx.HTTPError as exc:
                    # Sent, but no answer: it may have been acted on.
                    if attempt < attempts:
                        await self._backoff(attempt)
                        continue
                    raise ShippingProviderError(
                        "Shiprocket did not answer in time",
                        retryable=True,
                        ambiguous=not idempotent,
                    ) from exc

                status = response.status_code
                payload = _json(response)
                if status == httpx.codes.UNAUTHORIZED and not relogged:
                    # Expired or revoked token: the request was refused, so
                    # sending it again with a fresh token cannot double-book.
                    relogged = True
                    await self._forget_token()
                    attempt -= 1
                    continue
                if status in accept:
                    return payload
                if status == httpx.codes.TOO_MANY_REQUESTS:
                    if attempt < attempts:
                        await self._backoff(attempt, response.headers.get("Retry-After"))
                        continue
                    raise ShippingProviderError(
                        "Shiprocket's rate limit was reached; try again in a minute",
                        status_code=status,
                        retryable=True,
                    )
                if status >= 500:
                    if attempt < attempts:
                        await self._backoff(attempt)
                        continue
                    raise ShippingProviderError(
                        _error_message(payload, f"Shiprocket error (HTTP {status})"),
                        status_code=status,
                        retryable=True,
                        ambiguous=not idempotent,
                        details=payload,
                    )
                raise ShippingProviderError(
                    _error_message(payload, f"Shiprocket refused the request (HTTP {status})"),
                    status_code=status,
                    ambiguous=not idempotent and 200 <= status < 300,
                    details=payload,
                )

    async def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        delay = min(MAX_BACKOFF_SECONDS, 0.5 * 2 ** (attempt - 1))
        if retry_after and retry_after.isdigit():
            delay = min(MAX_BACKOFF_SECONDS, float(retry_after))
        await self._sleep(delay)

    # ------------------------------------------------------- operations

    async def check_rates(self, query: RateQuery) -> list[CourierRate]:
        payload = await self._request(
            "GET",
            "/courier/serviceability/",
            params={
                "pickup_postcode": query.pickup_postcode,
                "delivery_postcode": query.delivery_postcode,
                "cod": 1 if query.cod else 0,
                "weight": str(query.package.weight_kg),
                "length": str(query.package.length_cm),
                "breadth": str(query.package.breadth_cm),
                "height": str(query.package.height_cm),
                "declared_value": str(query.declared_value),
            },
            idempotent=True,
            accept=(200,),
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []
        recommended = _id(data.get("recommended_courier_company_id"))
        rates = []
        for company in data.get("available_courier_companies") or []:
            if not isinstance(company, dict) or _id(company.get("courier_company_id")) is None:
                continue
            courier_id = str(company["courier_company_id"])
            freight = _decimal(company.get("freight_charge"))
            cod_charge = _decimal(company.get("cod_charges"))
            rates.append(
                CourierRate(
                    courier_id=courier_id,
                    courier_name=_text(company.get("courier_name"), 100) or courier_id,
                    freight_charge=freight,
                    cod_charge=cod_charge,
                    total_charge=_decimal(company.get("rate")),
                    cod_available=_int(company.get("cod")) == 1,
                    etd=_text(company.get("etd"), 40),
                    estimated_delivery_days=_text(company.get("estimated_delivery_days"), 10),
                    is_recommended=courier_id == recommended,
                )
            )
        return rates

    async def create_order(self, booking: BookingRequest) -> BookedOrder:
        payload = await self._request(
            "POST",
            "/orders/create/adhoc",
            json=booking_payload(booking),
            idempotent=False,
            accept=(200,),
        )
        booked = _booked(
            {
                "id": payload.get("order_id") if isinstance(payload, dict) else None,
                "shipments": {
                    "id": payload.get("shipment_id"),
                    "awb": payload.get("awb_code"),
                    "courier_id": payload.get("courier_company_id"),
                    "courier": payload.get("courier_name"),
                }
                if isinstance(payload, dict)
                else None,
            }
        )
        if booked is None or booked.provider_shipment_id is None:
            # A 200 without the ids: we cannot tell what was created, so treat
            # it as ambiguous and reconcile by channel order id.
            raise ShippingProviderError(
                _error_message(payload, "Shiprocket did not return an order and shipment id"),
                ambiguous=True,
                retryable=True,
                details=payload,
            )
        return booked

    async def find_order(self, channel_order_id: str) -> BookedOrder | None:
        """Look an order up by the id we sent ("Search for AWB or by Channel order_id")."""
        payload = await self._request(
            "GET",
            "/orders",
            params={"search": channel_order_id},
            idempotent=True,
            accept=(200,),
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            if str(row.get("channel_order_id", "")).strip() != channel_order_id:
                continue
            return _booked(row)
        return None

    async def get_order(self, provider_order_id: str) -> BookedOrder | None:
        payload = await self._request(
            "GET",
            f"/orders/show/{provider_order_id}",
            idempotent=True,
            accept=(200,),
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return _booked(data) if isinstance(data, dict) else None

    async def assign_awb(self, shipment_id: str, courier_id: str | None) -> AwbAssignment:
        body: dict[str, Any] = {"shipment_id": _int(shipment_id) or shipment_id}
        if courier_id:
            body["courier_id"] = _int(courier_id) or courier_id
        payload = await self._request(
            "POST", "/courier/assign/awb", json=body, idempotent=False, accept=(200,)
        )
        response = payload.get("response") if isinstance(payload, dict) else None
        data = response.get("data") if isinstance(response, dict) else None
        data = data if isinstance(data, dict) else {}
        awb = _text(data.get("awb_code"), 64)
        if not isinstance(payload, dict) or _int(payload.get("awb_assign_status")) != 1 or not awb:
            raise ShippingProviderError(
                _text(data.get("awb_assign_error"))
                or _error_message(payload, "Shiprocket could not assign an AWB"),
                details=payload,
                ambiguous=not (
                    isinstance(payload, dict) and _int(payload.get("awb_assign_status")) == 0
                ),
            )
        return AwbAssignment(
            awb_code=awb,
            courier_id=_id(data.get("courier_company_id")),
            courier_name=_text(data.get("courier_name"), 100),
            applied_weight_kg=_decimal(data.get("applied_weight")),
            pickup_scheduled_date=_text(data.get("pickup_scheduled_date"), 40),
        )

    async def schedule_pickup(self, shipment_id: str, pickup_date: date | None) -> PickupResult:
        body: dict[str, Any] = {"shipment_id": [_int(shipment_id) or shipment_id]}
        if pickup_date is not None:
            body["pickup_date"] = [pickup_date.isoformat()]
        payload = await self._request(
            "POST", "/courier/generate/pickup", json=body, idempotent=False, accept=(200,)
        )
        response = payload.get("response") if isinstance(payload, dict) else None
        response = response if isinstance(response, dict) else {}
        if not isinstance(payload, dict) or _int(payload.get("pickup_status")) != 1:
            raise ShippingProviderError(
                _error_message(payload, "Shiprocket could not schedule the pickup"),
                details=payload,
                ambiguous=True,
            )
        return PickupResult(
            scheduled_date=_text(response.get("pickup_scheduled_date"), 40),
            token_number=_text(response.get("pickup_token_number"), 200),
        )

    async def generate_label(self, shipment_id: str) -> str:
        payload = await self._request(
            "POST",
            "/courier/generate/label",
            json={"shipment_id": [_int(shipment_id) or shipment_id]},
            idempotent=True,  # regenerating a label creates nothing new
            accept=(200,),
        )
        url = payload.get("label_url") if isinstance(payload, dict) else None
        if _int(payload.get("label_created") if isinstance(payload, dict) else None) != 1 or not (
            isinstance(url, str) and url.startswith("https://")
        ):
            raise ShippingProviderError(
                _error_message(payload, "Shiprocket could not create the label"),
                details=payload,
            )
        return url

    async def generate_manifest(self, shipment_id: str, provider_order_id: str) -> str:
        try:
            payload = await self._request(
                "POST",
                "/manifests/generate",
                json={"shipment_id": [_int(shipment_id) or shipment_id]},
                idempotent=False,
                accept=(200,),
            )
            url = payload.get("manifest_url") if isinstance(payload, dict) else None
        except ShippingProviderError as exc:
            # "Manifest already generated" -- print the existing one instead.
            already = (
                exc.details.get("already_manifested_shipment_ids")
                if isinstance(exc.details, dict)
                else None
            )
            if exc.status_code != 400 or not already:
                raise
            url = None
        if not url:
            printed = await self._request(
                "POST",
                "/manifests/print",
                json={"order_ids": [_int(provider_order_id) or provider_order_id]},
                idempotent=True,
                accept=(200,),
            )
            url = printed.get("manifest_url") if isinstance(printed, dict) else None
        if not (isinstance(url, str) and url.startswith("https://")):
            raise ShippingProviderError(
                "Shiprocket did not return a manifest. Schedule the pickup first."
            )
        return url

    async def track(self, awb_code: str) -> TrackingUpdate:
        payload = await self._request(
            "GET", f"/courier/track/awb/{awb_code}", idempotent=True, accept=(200,)
        )
        data = payload.get("tracking_data") if isinstance(payload, dict) else None
        data = data if isinstance(data, dict) else {}
        tracks = data.get("shipment_track")
        current = tracks[0] if isinstance(tracks, list) and tracks else {}
        current = current if isinstance(current, dict) else {}
        scans = [
            scan
            for entry in data.get("shipment_track_activities") or []
            if isinstance(entry, dict) and (scan := scan_from(entry)) is not None
        ]
        latest = max((scan.occurred_at for scan in scans), default=None)
        url = data.get("track_url")
        return TrackingUpdate(
            awb_code=awb_code,
            status_code=_int(data.get("shipment_status")),
            status_label=_text(current.get("current_status"), 100),
            occurred_at=latest,
            etd=_text(data.get("etd"), 40),
            track_url=url if isinstance(url, str) and url.startswith("https://") else None,
            courier_name=_text(current.get("courier_name"), 100),
            scans=scans,
            raw=payload if isinstance(payload, dict) else {},
        )

    async def cancel_order(self, provider_order_id: str) -> None:
        await self._request(
            "POST",
            "/orders/cancel",
            json={"ids": [_int(provider_order_id) or provider_order_id]},
            idempotent=False,
            accept=(204,),
        )

    async def pickup_locations(self) -> list[PickupLocation]:
        payload = await self._request(
            "GET", "/settings/company/pickup", idempotent=True, accept=(200,)
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("shipping_address") if isinstance(data, dict) else None
        return [
            PickupLocation(
                name=str(row.get("pickup_location")),
                postcode=_text(row.get("pin_code"), 6),
                city=_text(row.get("city")),
                state=_text(row.get("state")),
                is_primary=_int(row.get("is_primary_location")) == 1,
            )
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict) and row.get("pickup_location")
        ]


def _json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}
