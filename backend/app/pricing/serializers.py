"""Turn settings rows into API payloads."""

from __future__ import annotations

from app.core.money import ZERO
from app.pricing.models import GstSettings, PincodeRule, ShippingSettings, TaxSettings
from app.pricing.schemas import (
    GstSettingsRead,
    PincodeRuleRead,
    ShippingSettingsRead,
    TaxSettingsRead,
)


def shipping_read(settings: ShippingSettings | None) -> ShippingSettingsRead:
    """A tenant that has configured nothing charges nothing."""
    if settings is None:
        return ShippingSettingsRead(
            shipping_amount=ZERO, free_shipping_minimum=None, is_active=False
        )

    return ShippingSettingsRead(
        shipping_amount=settings.shipping_amount,
        free_shipping_minimum=settings.free_shipping_minimum,
        is_active=settings.is_active,
        min_delivery_days=settings.min_delivery_days,
        max_delivery_days=settings.max_delivery_days,
        restrict_to_listed_pincodes=settings.restrict_to_listed_pincodes,
    )


def tax_read(settings: TaxSettings | None) -> TaxSettingsRead:
    if settings is None:
        return TaxSettingsRead(tax_percentage=ZERO, is_active=False)

    return TaxSettingsRead(
        tax_percentage=settings.tax_percentage, is_active=settings.is_active,
        confirmed_by_ca=settings.confirmed_by_ca,
    )


def pincode_read(rule: PincodeRule) -> PincodeRuleRead:
    return PincodeRuleRead(
        pincode=rule.pincode,
        is_serviceable=rule.is_serviceable,
        cod_available=rule.cod_available,
        min_delivery_days=rule.min_delivery_days,
        max_delivery_days=rule.max_delivery_days,
        shipping_amount=rule.shipping_amount,
        city=rule.city,
        state=rule.state,
    )


def gst_read(settings: GstSettings | None) -> GstSettingsRead:
    if settings is None:
        return GstSettingsRead(is_system_default=True)
    return GstSettingsRead(
        gstin=settings.gstin,
        legal_name=settings.legal_name,
        address=settings.address,
        state=settings.state,
        state_code=settings.state_code,
        invoice_prefix=settings.invoice_prefix,
        shipping_sac_code=settings.shipping_sac_code,
        registration_status=settings.registration_status,
        accounting_software=settings.accounting_software,
        configuration_status=settings.configuration_status,
        prices_include_gst=settings.prices_include_gst,
        gst_enabled=settings.gst_enabled,
        default_classification=settings.default_classification,
        fallback_gst_rate=settings.fallback_gst_rate,
        defaults_reviewed_at=settings.defaults_reviewed_at,
        defaults_reviewed_by_id=settings.defaults_reviewed_by_id,
        updated_at=settings.updated_at,
        updated_by_id=settings.updated_by_id,
        confirmed_at=settings.confirmed_at,
        confirmed_by_id=settings.confirmed_by_id,
    )
