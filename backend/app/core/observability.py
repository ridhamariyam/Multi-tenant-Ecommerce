"""Logs, error reporting and alerts.

- Logs: one JSON object per line in staging/production (``LOG_FORMAT``), each
  carrying the request id, so a log collector can follow one request.
- Errors: unhandled exceptions go to Sentry when ``SENTRY_DSN`` is set.
  Request bodies, cookies and auth headers are never sent.
- Alerts: ``ALERT_WEBHOOK_URL`` (Slack/Discord/Google Chat style) gets one
  message per problem per ``ALERT_REPEAT_SECONDS``, never a flood.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)

_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-cart-token", "x-api-key"}
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

_sentry_enabled = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id != "-":
            entry["request_id"] = request_id
        # Anything passed as logger.info(..., extra={...}).
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_") and key != "color_message":
                entry[key] = value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(*, json_logs: bool, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_logs else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # uvicorn installs its own handlers; route its logs through ours instead.
    # Its access log is replaced by the API's own request log (app.main).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        uv.handlers[:] = []
        uv.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore", "botocore", "boto3", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _scrub(event: dict[str, Any], _hint: Any = None) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for key in list(headers):
                if key.lower() in _SENSITIVE_HEADERS:
                    headers[key] = "[filtered]"
    return event


def init_error_reporting(*, dsn: str | None, environment: str, release: str | None,
                         traces_sample_rate: float = 0.0, service: str = "api") -> bool:
    """Start Sentry if a DSN is set. Returns whether errors are being reported."""
    global _sentry_enabled
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; errors are only logged")
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_scrub,
    )
    sentry_sdk.set_tag("service", service)
    _sentry_enabled = True
    return True


def error_reporting_enabled() -> bool:
    return _sentry_enabled


def capture_exception(exc: BaseException, **tags: str) -> None:
    if not _sentry_enabled:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        for key, value in tags.items():
            scope.set_tag(key, value)
        request_id = get_request_id()
        if request_id != "-":
            scope.set_tag("request_id", request_id)
        sentry_sdk.capture_exception(exc)


async def send_alert(key: str, text: str) -> bool:
    """Post ``text`` to the alert webhook, at most once per key per repeat window.

    Never raises: alerting must not take down the thing it reports on.
    """
    from app.core.cache import get_redis
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.alert_webhook_url:
        return False
    try:
        first = await get_redis().set(
            f"cliq:alert:{key}", "1", nx=True, ex=settings.alert_repeat_seconds
        )
    except Exception:  # Redis down: alert anyway, that is worth knowing
        first = True
    if not first:
        return False
    message = f"[CliQ {settings.environment}] {text}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                settings.alert_webhook_url,
                # Slack and Google Chat read "text"; Discord reads "content".
                json={"text": message, "content": message},
            )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("alert webhook failed: %s", type(exc).__name__)
        return False
    return True
