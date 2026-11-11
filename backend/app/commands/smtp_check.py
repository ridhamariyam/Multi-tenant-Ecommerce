"""Check the configured SMTP server, and optionally send one test email.

    python -m app.commands.smtp_check                       # connect, TLS, log in; sends nothing
    python -m app.commands.smtp_check --to you@example.com  # ... and send a test email

Uses exactly the transport the outbox uses. Prints one JSON object: host,
port, TLS version and cipher, whether login succeeded, the sender, and the
Message-ID of the test email (search for it in the recipient's mailbox).
Never prints the password, and shows the username and recipient masked.
Exit code 0 only if every step succeeded.
"""

from __future__ import annotations

import argparse
import json
import smtplib
import sys
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.notifications import email
from app.notifications.models import OutboxEmail


def mask(address: str | None) -> str | None:
    if not address:
        return address
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def test_message(to: str) -> OutboxEmail:
    settings = get_settings()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    paragraphs = [
        "This is a test email from CliQ. to confirm outgoing mail works.",
        f"Sent {stamp} via {settings.smtp_host}:{settings.smtp_port} ({settings.smtp_security}).",
        "If this text is in a styled white card with a dark button, HTML rendering works.",
    ]
    return OutboxEmail(
        id=uuid.uuid4(),
        kind="smtp-check",
        dedupe_key=f"smtp-check:{uuid.uuid4()}",
        to_address=to,
        from_name=settings.email_from_name,
        subject=f"CliQ. SMTP test {stamp}",
        text_body="\n\n".join(paragraphs),
        html_body=email.simple_html("SMTP test", paragraphs, ("Open CliQ.", settings.console_base_url)),
        status="PENDING",
        attempts=0,
    )


def run(to: str | None) -> dict:
    settings = get_settings()
    report: dict = {
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "security": settings.smtp_security,
        "timeout_seconds": settings.smtp_timeout_seconds,
        "username": mask(settings.smtp_username),
        "from": f"{settings.email_from_name} <{settings.email_from_address}>",
        "connected": False,
        "authenticated": False,
    }
    if not settings.smtp_host:
        report["error"] = "SMTP_HOST is not set"
        return report
    transport = email.SmtpTransport()
    try:
        transport.open()
        report["connected"] = True
        report["tls"] = transport.tls or None
        report["authenticated"] = bool(settings.smtp_username)
        if to:
            message = email._build(test_message(to))
            transport.send(message)
            report["sent_to"] = mask(to)
            report["message_id"] = message["Message-ID"]
    except (smtplib.SMTPException, OSError) as exc:
        report["error"] = f"{type(exc).__name__}: {email._detail(exc)[:300]}"
        report["classified_as"] = email.classify(email.SmtpConnectError(exc) if not report["connected"] else exc)
    finally:
        transport.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", help="send one test email to this address")
    args = parser.parse_args()
    report = run(args.to)
    ok = "error" not in report and (not args.to or "message_id" in report)
    report["ok"] = ok
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
