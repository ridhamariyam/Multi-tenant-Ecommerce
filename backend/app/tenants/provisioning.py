"""The settings rows every brand needs before its checkout can price a basket."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pricing.constants import (
    SEED_FREE_SHIPPING_MINIMUM,
    SEED_SHIPPING_AMOUNT,
    SEED_TAX_PERCENTAGE,
)
from app.pricing.defaults import ensure_default_rules
from app.pricing.models import GstSettings, ShippingSettings, TaxSettings
from app.tenants.models import Tenant


def _silent(_: str) -> None:
    return None


async def ensure_tenant_defaults(
    session: AsyncSession, tenant: Tenant, *, log: Callable[[str], None] = _silent
) -> None:
    """Add whichever of the shipping, tax and GST settings rows is missing.

    Flushes but does not commit, so callers can include it in their own
    transaction (brand registration creates the brand and these together).
    """
    if await session.scalar(
        select(ShippingSettings).where(ShippingSettings.tenant_id == tenant.id)
    ) is None:
        session.add(
            ShippingSettings(
                tenant_id=tenant.id,
                shipping_amount=SEED_SHIPPING_AMOUNT,
                free_shipping_minimum=SEED_FREE_SHIPPING_MINIMUM,
                is_active=True,
            )
        )
        log(
            f"Created shipping settings: {SEED_SHIPPING_AMOUNT} "
            f"(free over {SEED_FREE_SHIPPING_MINIMUM})"
        )
    else:
        log("Shipping settings already exist")

    if await session.scalar(select(TaxSettings).where(TaxSettings.tenant_id == tenant.id)) is None:
        session.add(
            TaxSettings(
                tenant_id=tenant.id,
                tax_percentage=SEED_TAX_PERCENTAGE,
                is_active=False,
                confirmed_by_ca=False,
            )
        )
        log(f"Created pending tax settings: {SEED_TAX_PERCENTAGE}%")
    else:
        log("Tax settings already exist")

    # Platform defaults only: no GSTIN, state or legal name is assumed. Checkout
    # prices with the unverified system rules until the store reviews them.
    if await session.scalar(select(GstSettings).where(GstSettings.tenant_id == tenant.id)) is None:
        session.add(GstSettings(tenant_id=tenant.id))
        log("Created draft GST settings with the system defaults (awaiting verification)")
    else:
        log("GST settings already exist")

    added = await ensure_default_rules(session, commit=False)
    log(f"System GST default rules: {added} added" if added else "System GST rules present")
    await session.flush()
