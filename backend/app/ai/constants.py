from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"  # accepted, not yet sent to the provider
    STARTING = "starting"  # sent; provider is initialising or queueing it
    PROCESSING = "processing"  # provider is generating
    COMPLETED = "completed"  # outputs stored in our bucket
    FAILED = "failed"
    CANCELLED = "cancelled"


JOB_STATUSES = tuple(s.value for s in JobStatus)
ACTIVE_STATUSES = frozenset({JobStatus.QUEUED.value, JobStatus.STARTING.value, JobStatus.PROCESSING.value})
FINAL_STATUSES = frozenset({JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value})


class LedgerEntry(str, Enum):
    GRANT = "GRANT"  # credits added (plan allowance, admin top-up)
    RESERVE = "RESERVE"  # held when a job is accepted (negative)
    RELEASE = "RELEASE"  # the hold returned when the job ends (positive)
    CHARGE = "CHARGE"  # what a completed job actually cost (negative)
    ADJUST = "ADJUST"  # manual correction by a platform admin


LEDGER_ENTRIES = tuple(e.value for e in LedgerEntry)

# Settings brands may choose (FASHN tryon-max contract, docs read 2026-11-07).
RESOLUTIONS = ("1k", "2k", "4k")
GENERATION_MODES = ("fast", "balanced", "quality")
OUTPUT_FORMATS = ("png", "jpeg")
MAX_IMAGES_PER_JOB = 4

# Internal credits per output image. Deliberately separate from what the
# provider bills us (recorded per job as provider_credits).
CREDITS_PER_IMAGE = {
    ("fast", "1k"): 1, ("fast", "2k"): 2, ("fast", "4k"): 3,
    ("balanced", "1k"): 2, ("balanced", "2k"): 3, ("balanced", "4k"): 4,
    ("quality", "1k"): 3, ("quality", "2k"): 4, ("quality", "4k"): 5,
}  # fmt: skip


def credits_for(mode: str, resolution: str, images: int) -> int:
    return CREDITS_PER_IMAGE[(mode, resolution)] * images
