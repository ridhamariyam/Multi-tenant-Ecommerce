from enum import Enum


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


ACCOUNT_STATUSES = tuple(s.value for s in AccountStatus)

MIN_PASSWORD_LENGTH = 10
