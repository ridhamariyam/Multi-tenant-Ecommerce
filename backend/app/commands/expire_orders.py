"""Cancel unpaid online orders past ONLINE_PAYMENT_EXPIRY_MINUTES; run it from cron."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, dispose_engine
from app.orders.service import OrderService
from app.tenants.models import Tenant


async def expire_orders() -> bool:
    """Expire unpaid online orders for every active tenant; False if any tenant failed."""
    succeeded = True
    async with AsyncSessionLocal() as session:
        tenant_ids = (
            await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
        ).all()

    for tenant_id in tenant_ids:
        async with AsyncSessionLocal() as session:
            try:
                expired = await OrderService(session, tenant_id).expire_unpaid_online()
            except Exception as exc:
                print(f"Tenant {tenant_id}: expiry failed ({type(exc).__name__})", file=sys.stderr)
                succeeded = False
                continue
        print(f"Tenant {tenant_id}: {expired} unpaid order(s) expired.")

    await dispose_engine()
    return succeeded


def main() -> None:
    if not asyncio.run(expire_orders()):
        sys.exit(1)


if __name__ == "__main__":
    main()
