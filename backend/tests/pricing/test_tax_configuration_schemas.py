"""Input validation for versioned, CA-confirmed product tax mappings."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.pricing.schemas import GstSettingsUpdate, TaxRateConfigurationWrite


def test_tax_rate_requires_exactly_one_product_or_category():
    with pytest.raises(ValidationError):
        TaxRateConfigurationWrite(hsn_code="6204", gst_rate="5.00", effective_from="2026-10-01")
    with pytest.raises(ValidationError):
        TaxRateConfigurationWrite(
            product_id=uuid4(), category_id=uuid4(), hsn_code="6204",
            gst_rate="5.00", effective_from="2026-10-01",
        )


def test_tax_rate_validates_hsn_and_decimal_rate_without_legal_defaults():
    config = TaxRateConfigurationWrite(
        category_id=uuid4(), hsn_code="6204", gst_rate="5.00",
        effective_from="2026-10-01",
    )
    assert config.ca_confirmed is False
    assert config.gst_rate.as_tuple().exponent == -2
    with pytest.raises(ValidationError):
        TaxRateConfigurationWrite(
            category_id=uuid4(), hsn_code="not-hsn", gst_rate="5.00",
            effective_from="2026-10-01",
        )
    with pytest.raises(ValidationError):
        TaxRateConfigurationWrite(
            category_id=uuid4(), hsn_code="6204", gst_rate="100.01",
            effective_from="2026-10-01",
        )


def test_business_gst_configuration_starts_unconfirmed():
    settings = GstSettingsUpdate(
        legal_name="Example Legal Name", address="Example Registered Address",
        state="Karnataka", registration_status="NOT_REGISTERED",
    )
    assert settings.configuration_status == "DRAFT"
    assert settings.prices_include_gst is False
