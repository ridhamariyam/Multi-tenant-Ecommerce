"""URL slugs shared by products and CMS content."""

from __future__ import annotations

import re
import unicodedata

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def slugify(text: str, max_length: int = 120, fallback: str = "untitled") -> str:
    """'Cotton Kurta – Navy Blue!' -> 'cotton-kurta-navy-blue'. Accents are folded to ASCII."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].strip("-") or fallback


def with_suffix(slug: str, n: int, max_length: int = 120) -> str:
    """The n-th alternative for a taken slug: base-2, base-3, ... kept within max_length."""
    suffix = f"-{n}"
    return slug[: max_length - len(suffix)].rstrip("-") + suffix
