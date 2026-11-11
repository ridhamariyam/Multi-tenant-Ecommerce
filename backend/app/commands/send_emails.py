"""Queue order confirmations, then deliver every due email.

    python -m app.commands.send_emails      # one pass (the scheduler runs it every 30 s)
"""

from __future__ import annotations

import asyncio

from app.core.database import AsyncSessionLocal, dispose_engine
from app.notifications import email
from app.marketing.service import queue_cart_reminders
from app.notifications.orders import queue_order_confirmations


async def send_emails() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        queued = await queue_order_confirmations(session)
        queued += await queue_cart_reminders(session)
        delivered = await email.send_due(session)
    return {"queued": queued, **delivered}


async def _once() -> dict[str, int]:
    try:
        return await send_emails()
    finally:
        await dispose_engine()


def main() -> None:
    print(asyncio.run(_once()))


if __name__ == "__main__":
    main()
