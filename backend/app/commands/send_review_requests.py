"""Send every due automatic review request, for every tenant.

Run on a schedule, e.g. hourly:  python -m app.commands.send_review_requests

Uses a no-op notifier until an email/SMS/WhatsApp channel is connected.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, dispose_engine
from app.ratings.service import ReviewRequestService
from app.tenants.models import Tenant


async def send_review_requests() -> dict[str, int]:
    totals = {"sent": 0, "completed": 0}
    async with AsyncSessionLocal() as session:
        tenant_ids = (await session.scalars(select(Tenant.id))).all()
        for tenant_id in tenant_ids:
            result = await ReviewRequestService(session, tenant_id).dispatch_due()
            totals["sent"] += result["sent"]
            totals["completed"] += result["completed"]
    await dispose_engine()
    return totals


def main() -> None:
    totals = asyncio.run(send_review_requests())
    print(f"Review requests: {totals['sent']} sent, {totals['completed']} closed.")


if __name__ == "__main__":
    main()
