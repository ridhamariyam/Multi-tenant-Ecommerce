from __future__ import annotations

import re
from decimal import Decimal

from app.chatbot.schemas import QueryUnderstandingInput, SearchCriteria

_COLORS = (
    "navy blue", "sky blue", "royal blue", "off white", "off-white", "dark green",
    "light green", "maroon", "purple", "violet", "yellow", "orange", "pink",
    "white", "black", "blue", "green", "red", "brown", "beige", "cream", "grey",
    "gray", "gold", "silver", "teal",
)
_FABRICS = (
    "organic cotton", "cotton", "silk", "linen", "rayon", "georgette", "chiffon",
    "velvet", "denim", "wool", "viscose", "chanderi", "chikankari",
)
_OCCASIONS = (
    "wedding", "festive", "festival", "party", "casual", "office", "everyday",
    "daily wear", "formal",
)
_SIZE_ALIASES = {
    "extra small": "XS", "x-small": "XS", "xs": "XS",
    "small": "S", "s": "S",
    "medium": "M", "m": "M",
    "large": "L", "l": "L",
    "extra large": "XL", "x-large": "XL", "xl": "XL",
    "xxl": "XXL", "2xl": "XXL", "xxxl": "XXXL", "3xl": "XXXL",
}


def _phrase_pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    choices = sorted((re.escape(value) for value in phrases), key=len, reverse=True)
    return re.compile(r"(?<![\w])(?:" + "|".join(choices) + r")(?![\w])", re.IGNORECASE)


_COLOR_PATTERN = _phrase_pattern(_COLORS)
_FABRIC_PATTERN = _phrase_pattern(_FABRICS)
_OCCASION_PATTERN = _phrase_pattern(_OCCASIONS)
_SIZE_PATTERN = re.compile(
    r"(?<![\w])(?:size\s+)?(extra\s+small|x-small|extra\s+large|x-large|"
    r"small|medium|large|xs|xl|xxxl|xxl|3xl|2xl|s|m|l)(?:\s+size)?(?![\w])",
    re.IGNORECASE,
)

_AMOUNT = r"(?:₹\s*)?([+-]?\d[\d,]*(?:\.\d{1,2})?)(?:\s*(?:rupees?|rs\.?))?"
_BETWEEN_PATTERN = re.compile(
    rf"(?<![\w])between\s+{_AMOUNT}\s+and\s+{_AMOUNT}(?![\w])", re.IGNORECASE
)
_LIMIT_PATTERN = re.compile(
    rf"(?<![\w])(?P<operator>under|below|less\s+than|up\s+to|at\s+most|"
    rf"above|over|more\s+than|at\s+least)\s+{_AMOUNT}(?![\w])",
    re.IGNORECASE,
)
_MALFORMED_NEGATIVE_PRICE = re.compile(
    r"(?<![\w])(?:under|below|above|over|between|less\s+than|more\s+than)\s+(?:₹\s*)?[-−]\s*\d",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+")
_EDGE_PUNCTUATION = re.compile(r"^[\s,.;:!?/-]+|[\s,.;:!?/-]+$")


def _one_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    return pattern.search(text)


def _clean_search(text: str) -> str | None:
    # These short connector words remain after recognized phrases are removed.
    text = re.sub(r"(?i)\b(?:for|a|an|the)\b", " ", text)
    text = re.sub(r"[,;]", " ", text)
    text = _EDGE_PUNCTUATION.sub("", text)
    text = _SPACE.sub(" ", text).strip()
    return text or None


def understand_query(payload: QueryUnderstandingInput | str) -> SearchCriteria:
    """Extract a small, explicit set of shopping filters without external data.

    Recognition is deliberately phrase-based. Anything not recognized as one
    of these bounded criteria remains in ``search`` instead of being guessed.
    """
    request = QueryUnderstandingInput(message=payload) if isinstance(payload, str) else payload

    remaining = request.message.strip()
    if not remaining:
        return SearchCriteria()

    if _MALFORMED_NEGATIVE_PRICE.search(remaining):
        raise ValueError("Price limits cannot be negative")

    found_spans: list[tuple[int, int]] = []
    min_price: Decimal | None = None
    max_price: Decimal | None = None

    between = _one_match(_BETWEEN_PATTERN, remaining)
    if between:
        min_price = Decimal(between.group(1).replace(",", ""))
        max_price = Decimal(between.group(2).replace(",", ""))
        found_spans.append(between.span())
    else:
        for match in _LIMIT_PATTERN.finditer(remaining):
            amount = Decimal(match.group(2).replace(",", ""))
            operator = re.sub(r"\s+", " ", match.group("operator").lower())
            if operator in {"under", "below", "less than", "up to", "at most"}:
                max_price = amount
            else:
                min_price = amount
            found_spans.append(match.span())

    color_match = _one_match(_COLOR_PATTERN, remaining)
    color = color_match.group(0).title() if color_match else None
    if color_match:
        found_spans.append(color_match.span())

    size_match = _one_match(_SIZE_PATTERN, remaining)
    size = None
    if size_match:
        size = _SIZE_ALIASES[size_match.group(1).lower()]
        found_spans.append(size_match.span())

    fabric_match = _one_match(_FABRIC_PATTERN, remaining)
    fabric = fabric_match.group(0).title() if fabric_match else None
    if fabric_match:
        found_spans.append(fabric_match.span())

    occasion_match = _one_match(_OCCASION_PATTERN, remaining)
    occasion = occasion_match.group(0).title() if occasion_match else None
    if occasion_match:
        found_spans.append(occasion_match.span())

    # Replace extracted spans from right to left so original offsets remain valid.
    for start, end in sorted(found_spans, reverse=True):
        remaining = remaining[:start] + " " + remaining[end:]

    return SearchCriteria(
        search=_clean_search(remaining),
        color=color,
        size=size,
        fabric=fabric,
        occasion=occasion,
        min_price=min_price,
        max_price=max_price,
    )
