"""Provider concurrency: at most N jobs in flight per provider, across all workers."""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from app.core.cache import get_redis

_KEY = "ai:provider-slots:{}"

# Drop expired holders, then take a slot if one is free (or already ours).
_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZSCORE', KEYS[1], ARGV[2]) then return 1 end
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[3]) then
  redis.call('ZADD', KEYS[1], ARGV[4], ARGV[2])
  return 1
end
return 0
"""


async def acquire_slot(provider: str, job_id: uuid.UUID, limit: int, until: datetime) -> bool:
    try:
        result = await get_redis().eval(
            _ACQUIRE, 1, _KEY.format(provider), time.time(), str(job_id), limit, until.timestamp()
        )
    except Exception:
        # Redis unavailable: do not block generation; the provider's own 429
        # (ConcurrencyLimitExceeded) is retried by the worker.
        return True
    return bool(result)


async def release_slot(provider: str, job_id: uuid.UUID) -> None:
    try:
        await get_redis().zrem(_KEY.format(provider), str(job_id))
    except Exception:
        return  # the entry expires with the job's timeout
