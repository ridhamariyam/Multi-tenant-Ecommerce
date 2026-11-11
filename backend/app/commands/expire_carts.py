"""Expire carts idle longer than CART_RETENTION_DAYS (30 by default).

Run on a schedule, e.g. daily:  python -m app.commands.expire_carts

Carts also expire lazily the next time their owner opens them, so this job
only keeps abandoned carts from holding rows forever.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.cart.repository import expire_stale_carts
from app.cart.service import retention_period
from app.core.database import AsyncSessionLocal, dispose_engine


async def expire_carts() -> int:
    cutoff = datetime.now(timezone.utc) - retention_period()
    async with AsyncSessionLocal() as session:
        expired = await expire_stale_carts(session, cutoff)
        await session.commit()
    await dispose_engine()
    return expired


def main() -> None:
    expired = asyncio.run(expire_carts())
    print(f"Expired {expired} cart(s) idle since before the retention period.")


if __name__ == "__main__":
    main()
