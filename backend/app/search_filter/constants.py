from enum import Enum


class SearchSort(str, Enum):
    """Sort orders the storefront search accepts. Anything else is a 422."""

    RECOMMENDED = "RECOMMENDED"
    NEWEST = "NEWEST"
    PRICE_LOW = "price"
    PRICE_HIGH = "-price"


COLOR_OPTION = "Color"
SIZE_OPTION = "Size"

MAX_SUGGESTIONS = 10
MAX_HISTORY_ENTRIES = 10
MAX_QUERY_LENGTH = 255
