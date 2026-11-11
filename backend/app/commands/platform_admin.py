"""Grant or revoke platform administration for a merchant account.

    python -m app.commands.platform_admin grant  someone@example.com
    python -m app.commands.platform_admin revoke someone@example.com
    python -m app.commands.platform_admin list

There is deliberately no API for this: the first platform administrator has
to be made by someone with shell access to the deployment.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, dispose_engine
from app.merchants.models import MerchantAccount


async def run(action: str, email: str | None) -> int:
    async with AsyncSessionLocal() as session:
        if action == "list":
            admins = await session.scalars(
                select(MerchantAccount)
                .where(MerchantAccount.is_platform_admin.is_(True))
                .order_by(MerchantAccount.email)
            )
            for account in admins:
                print(account.email)
            return 0

        account = await session.scalar(
            select(MerchantAccount).where(MerchantAccount.email == (email or "").strip().lower())
        )
        if account is None:
            print(f"No merchant account with email {email!r}")
            return 1
        account.is_platform_admin = action == "grant"
        await session.commit()
        print(f"{account.email}: platform admin {'granted' if action == 'grant' else 'revoked'}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("grant", "revoke", "list"))
    parser.add_argument("email", nargs="?")
    args = parser.parse_args()
    if args.action != "list" and not args.email:
        parser.error("an email is required")

    async def _main() -> int:
        try:
            return await run(args.action, args.email)
        finally:
            await dispose_engine()

    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
