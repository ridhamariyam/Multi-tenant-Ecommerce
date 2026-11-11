"""Prove a brand controls a custom domain: the TXT record at
`_cliq-verify.<domain>` must contain `cliq-verify=<token>`.

Only a DNS query is made (no HTTP request to the domain), so this cannot be
used to reach internal services. Lookups time out quickly and a failure is
reported, never treated as success.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import dns.asyncresolver
import dns.exception
import dns.resolver

VERIFY_PREFIX = "_cliq-verify"
LOOKUP_TIMEOUT_SECONDS = 5.0


@dataclass
class DnsCheck:
    verified: bool
    record_name: str
    expected: str
    found: list[str] = field(default_factory=list)
    problem: str | None = None


async def lookup_txt(name: str) -> list[str]:
    """TXT strings at `name`; [] when there are none. Raises on resolver failure."""
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = LOOKUP_TIMEOUT_SECONDS
    try:
        answer = await resolver.resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    return [b"".join(rdata.strings).decode("utf-8", "replace") for rdata in answer]


async def check_ownership(domain: str, token: str | None) -> DnsCheck:
    name = f"{VERIFY_PREFIX}.{domain}"
    expected = f"cliq-verify={token}" if token else ""
    if not token:
        return DnsCheck(False, name, expected, problem="This domain has no verification token.")
    try:
        found = await lookup_txt(name)
    except (dns.exception.Timeout, dns.resolver.NoNameservers):
        return DnsCheck(False, name, expected, problem="DNS did not answer. Try again in a few minutes.")
    except dns.exception.DNSException:
        return DnsCheck(False, name, expected, problem="The DNS lookup failed. Check the domain name.")
    if expected in (value.strip() for value in found):
        return DnsCheck(True, name, expected, found)
    problem = (
        "The TXT record was not found yet. DNS changes can take up to 48 hours."
        if not found
        else "A TXT record exists but does not contain the expected value."
    )
    return DnsCheck(False, name, expected, found, problem)
