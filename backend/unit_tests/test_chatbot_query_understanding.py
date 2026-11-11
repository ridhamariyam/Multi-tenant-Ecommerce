from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.chatbot.query_understanding import understand_query
from app.chatbot.schemas import QueryUnderstandingInput, SearchCriteria


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Orange kurta, medium size, Anarkali.",
            SearchCriteria(search="kurta Anarkali", color="Orange", size="M"),
        ),
        (
            "Black kurta under ₹1500.",
            SearchCriteria(search="kurta", color="Black", max_price=Decimal("1500")),
        ),
        (
            "Cotton kurta for a wedding.",
            SearchCriteria(search="kurta", fabric="Cotton", occasion="Wedding"),
        ),
        (
            "kurta below 1500 rupees",
            SearchCriteria(search="kurta", max_price=Decimal("1500")),
        ),
        (
            "kurta above ₹800",
            SearchCriteria(search="kurta", min_price=Decimal("800")),
        ),
        (
            "kurta between ₹800 and ₹1,500",
            SearchCriteria(
                search="kurta", min_price=Decimal("800"), max_price=Decimal("1500")
            ),
        ),
        (
            "navy blue silk kurta for a party, size XL",
            SearchCriteria(
                search="kurta", color="Navy Blue", fabric="Silk", occasion="Party", size="XL"
            ),
        ),
        ("", SearchCriteria()),
        ("   ", SearchCriteria()),
        ("Anarkali festive outfit", SearchCriteria(search="Anarkali outfit", occasion="Festive")),
        (
            "kurta under ₹0",
            SearchCriteria(search="kurta", max_price=Decimal("0")),
        ),
        (
            "kurta between 0 and 800",
            SearchCriteria(search="kurta", min_price=Decimal("0"), max_price=Decimal("800")),
        ),
        (
            "kurta between 800 and",
            SearchCriteria(search="kurta between 800 and"),
        ),
    ],
)
def test_understands_bounded_shopping_criteria(message, expected):
    assert understand_query(message) == expected


def test_accepts_strict_input_schema():
    assert understand_query(QueryUnderstandingInput(message="kurta size medium")) == SearchCriteria(
        search="kurta", size="M"
    )


@pytest.mark.parametrize("message", ["kurta under -800", "kurta above ₹-1"])
def test_rejects_negative_price_limits(message):
    with pytest.raises(ValueError, match="cannot be negative"):
        understand_query(message)


@pytest.mark.parametrize(
    "message",
    ["kurta under 800 above 1500", "kurta between 1500 and 800"],
)
def test_rejects_conflicting_price_limits(message):
    with pytest.raises(ValidationError, match="min_price cannot be greater"):
        understand_query(message)


def test_strict_input_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        QueryUnderstandingInput(message="kurta", extra="ignored")
