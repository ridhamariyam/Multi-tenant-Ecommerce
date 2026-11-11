"""Reconcile unconfirmed Shiprocket bookings and refresh tracking; run it from cron.

Webhooks deliver most tracking updates; this catches the ones that never
arrive. It only looks bookings up, it never books -- an unconfirmed booking
that Shiprocket does not know is left for an admin to Retry.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, dispose_engine
from app.shipments import shiprocket
from app.shipments.models import ShippingProviderSettings
from app.shipments.service import ShipmentService
from app.tenants.models import Tenant


async def sync_shipments() -> bool:
    """One pass over every tenant with shipping enabled; False if any tenant failed."""
    succeeded = True
    async with AsyncSessionLocal() as session:
        tenant_ids = (
            await session.scalars(
                select(Tenant.id)
                .join(ShippingProviderSettings, ShippingProviderSettings.tenant_id == Tenant.id)
                .where(Tenant.is_active.is_(True), ShippingProviderSettings.is_enabled.is_(True))
            )
        ).all()

    for tenant_id in tenant_ids:
        if not shiprocket.is_configured(tenant_id):
            print(f"Tenant {tenant_id}: credentials are not configured; skipped.")
            continue
        async with AsyncSessionLocal() as session:
            try:
                counts = await ShipmentService(session, tenant_id).run_background_sync()
            except Exception as exc:
                print(f"Tenant {tenant_id}: sync failed ({type(exc).__name__})", file=sys.stderr)
                succeeded = False
                continue
        if counts["failed"]:
            succeeded = False
        print(
            f"Tenant {tenant_id}: {counts['tracked']} tracked, "
            f"{counts['reconciled']} reconciled, {counts['failed']} failed."
        )

    await dispose_engine()
    return succeeded


def main() -> None:
    if not asyncio.run(sync_shipments()):
        sys.exit(1)


if __name__ == "__main__":
    main()
