"""Append every store's new sales to its Google Sheet.

    python -m app.commands.sync_order_sheets            # one pass, for cron
    python -m app.commands.sync_order_sheets --loop 60  # run forever, every 60 s

Does nothing until the server has a Google service account key and a store
has connected a spreadsheet (Admin > Integrations > Google Sheets).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, dispose_engine
from app.integrations import google_sheets
from app.integrations.models import OrderSheetSettings
from app.integrations.order_sheets import OrderSheetService
from app.tenants.models import Tenant


async def sync_order_sheets() -> bool:
    """One pass over every store with the export on; False if any store failed."""
    if not google_sheets.is_configured():
        return True

    async with AsyncSessionLocal() as session:
        tenant_ids = (
            await session.scalars(
                select(Tenant.id)
                .join(OrderSheetSettings, OrderSheetSettings.tenant_id == Tenant.id)
                .where(
                    Tenant.is_active.is_(True),
                    OrderSheetSettings.is_enabled.is_(True),
                    OrderSheetSettings.spreadsheet_id.is_not(None),
                )
            )
        ).all()

    succeeded = True
    for tenant_id in tenant_ids:
        async with AsyncSessionLocal() as session:
            try:
                result = await OrderSheetService(session, tenant_id).sync()
            except Exception as exc:
                print(f"Tenant {tenant_id}: sheet export crashed ({type(exc).__name__})", file=sys.stderr)
                succeeded = False
                continue
        if result.error:
            print(f"Tenant {tenant_id}: sheet export failed: {result.error}", file=sys.stderr)
            succeeded = False
        elif result.exported:
            print(f"Tenant {tenant_id}: {result.exported} order(s) written to the sheet.")
    return succeeded


async def run(loop_seconds: int | None) -> bool:
    try:
        if loop_seconds is None:
            return await sync_order_sheets()
        while True:
            try:
                await sync_order_sheets()
            except Exception as exc:  # keep the worker alive through a DB blip
                print(f"Sheet export pass failed ({type(exc).__name__})", file=sys.stderr)
            await asyncio.sleep(loop_seconds)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--loop", type=int, metavar="SECONDS", help="repeat forever")
    args = parser.parse_args()
    if args.loop is not None and args.loop < 5:
        parser.error("--loop must be at least 5 seconds")
    if not asyncio.run(run(args.loop)):
        sys.exit(1)


if __name__ == "__main__":
    main()
