"""Automatic activity log for admin write endpoints.

Attach `AUDITED` to an admin router's `dependencies`. After an endpoint
succeeds, a POST/PUT/PATCH/DELETE is recorded: who (the signed-in user),
what (the endpoint and the request body, secrets scrubbed), which record
(the first path parameter), from where (IP) and when. A request that fails
or is refused raises through the `yield`, so it is never logged as done.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_activity
from app.auth.dependencies import CurrentUser
from app.core.database import get_db

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_BODY_BYTES = 20_000

# A path parameter names the record; anything else falls back to the URL.
_ENTITY_ALIASES = {"entry": "cod_blacklist", "staff": "staff"}


def _entity(request: Request) -> tuple[str, str | None]:
    params = request.path_params
    if params:
        name, value = next(iter(params.items()))
        base = name[:-3] if name.endswith("_id") else name
        return _ENTITY_ALIASES.get(base, base), str(value)
    path = getattr(request.scope.get("route"), "path", request.url.path)
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    last = segments[-1] if segments else "unknown"
    return _singular(last), None


async def _body(request: Request):
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        return {"upload": True}
    if "application/json" not in content_type:
        return None
    raw = await request.body()
    if not raw or len(raw) > MAX_BODY_BYTES:
        return None if not raw else {"truncated": True}
    try:
        return json.loads(raw)
    except ValueError:
        return None


async def audit_trail(
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[None, None]:
    yield
    if request.method not in MUTATING or getattr(request.state, "audit_recorded", False):
        return
    route = request.scope.get("route")
    entity_type, entity_id = _entity(request)
    try:
        await record_activity(
            session,
            user,
            getattr(route, "name", request.method.lower()),
            entity_type,
            entity_id,
            summary=getattr(route, "summary", None),
            changes={
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params) or None,
                "body": await _body(request),
            },
            request=request,
        )
    except Exception:  # the action itself already succeeded; never fail it here
        await session.rollback()


AUDITED = [Depends(audit_trail)]


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith(("ss", "us")):
        return word[:-1]
    return word
