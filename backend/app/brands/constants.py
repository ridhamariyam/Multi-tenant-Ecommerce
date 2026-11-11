"""Brand membership roles and what each grants in the existing admin."""

from __future__ import annotations

from enum import Enum

from app.auth.constants import UserRole
from app.auth.permissions import Permission


class BrandRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    PRODUCT_MANAGER = "PRODUCT_MANAGER"
    ORDER_MANAGER = "ORDER_MANAGER"
    # A login that existed before memberships did, whose permissions were set
    # one by one on the staff screen. Its permissions are left as they were.
    CUSTOM = "CUSTOM"


BRAND_ROLES = tuple(r.value for r in BrandRole)

# Roles that may manage the brand itself: profile, members, store, domains.
BRAND_MANAGER_ROLES = frozenset({BrandRole.OWNER.value, BrandRole.ADMIN.value})


class MemberStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"


MEMBER_STATUSES = tuple(s.value for s in MemberStatus)


_PRODUCT_MANAGER = frozenset(
    {
        Permission.DASHBOARD_VIEW,
        Permission.CATALOGUE_VIEW,
        Permission.CATALOGUE_MANAGE,
        Permission.REVIEWS_VIEW,
        Permission.REVIEWS_MANAGE,
        Permission.COUPONS_VIEW,
        Permission.CMS_VIEW,
        Permission.CMS_MANAGE,
    }
)

_ORDER_MANAGER = frozenset(
    {
        Permission.DASHBOARD_VIEW,
        Permission.ORDERS_VIEW,
        Permission.ORDERS_MANAGE,
        Permission.CUSTOMERS_VIEW,
        Permission.CUSTOMERS_MANAGE,
        Permission.PAYMENTS_VIEW,
        Permission.PAYMENTS_MANAGE,
        Permission.CATALOGUE_VIEW,
    }
)


def admin_user_for_role(role: str) -> tuple[str, list[str] | None]:
    """The (users.role, users.permissions) a membership role maps onto.

    Owners and admins are full ADMIN users. The managers are STAFF with a
    fixed permission set, so every existing admin endpoint enforces them
    without change.
    """
    if role in (BrandRole.OWNER.value, BrandRole.ADMIN.value):
        return UserRole.ADMIN.value, None
    if role == BrandRole.PRODUCT_MANAGER.value:
        return UserRole.STAFF.value, sorted(p.value for p in _PRODUCT_MANAGER)
    if role == BrandRole.ORDER_MANAGER.value:
        return UserRole.STAFF.value, sorted(p.value for p in _ORDER_MANAGER)
    raise ValueError(f"Role {role!r} has no fixed permission set")
