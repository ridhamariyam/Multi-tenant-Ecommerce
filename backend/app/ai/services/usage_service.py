"""AI credit accounting on an append-only ledger.

Balance = sum of entries. A job RESERVEs its estimate up front; when it ends
it RELEASEs the hold and, if it produced images, is CHARGEd for what it
produced. Each of those exists at most once per job (unique constraint), so
repeated tasks or webhooks cannot bill twice. Failed and cancelled jobs are
only released: they cost nothing.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.constants import LedgerEntry
from app.ai.models import AiUsageLedger
from app.core.error_codes import AiErrorCode
from app.core.exceptions import AppError


class InsufficientCreditsError(AppError):
    status_code = 402
    error_code = AiErrorCode.INSUFFICIENT_CREDITS
    default_message = "Not enough AI credits"


async def lock_brand_credits(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Serialise credit checks for one brand until the transaction ends."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"ai-credits:{tenant_id}"},
    )


async def balance(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(AiUsageLedger.credits), 0)).where(
            AiUsageLedger.tenant_id == tenant_id
        )
    )
    return int(total or 0)


async def _entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    entry_type: LedgerEntry,
    credits: int,
    note: str | None = None,
) -> bool:
    """Insert one job entry. False if it already existed (a repeat)."""
    result = await session.execute(
        insert(AiUsageLedger)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            job_id=job_id,
            entry_type=entry_type.value,
            credits=credits,
            note=note,
        )
        .on_conflict_do_nothing(constraint="uq_ai_usage_ledger_job_entry")
        .returning(AiUsageLedger.id)
    )
    return result.scalar_one_or_none() is not None


async def reserve(session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID, credits: int) -> None:
    """Hold credits for a new job. Call after lock_brand_credits, in the job's transaction."""
    available = await balance(session, tenant_id)
    if available < credits:
        raise InsufficientCreditsError(
            f"This generation needs {credits} AI credits; {max(available, 0)} available."
        )
    await _entry(session, tenant_id, job_id, LedgerEntry.RESERVE, -credits)


async def settle(
    session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID, *, reserved: int, charge: int
) -> bool:
    """Release the hold and charge `charge` (0 for failed/cancelled). Idempotent."""
    released = await _entry(session, tenant_id, job_id, LedgerEntry.RELEASE, reserved)
    if charge > 0:
        await _entry(session, tenant_id, job_id, LedgerEntry.CHARGE, -charge)
    return released


async def grant(
    session: AsyncSession, tenant_id: uuid.UUID, credits: int, *, reference: str, note: str | None
) -> bool:
    result = await session.execute(
        insert(AiUsageLedger)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entry_type=LedgerEntry.GRANT.value if credits >= 0 else LedgerEntry.ADJUST.value,
            credits=credits,
            reference=reference,
            note=note,
        )
        .on_conflict_do_nothing(constraint="uq_ai_usage_ledger_reference")
        .returning(AiUsageLedger.id)
    )
    return result.scalar_one_or_none() is not None
