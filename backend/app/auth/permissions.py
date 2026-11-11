"""Fine-grained admin permissions.

ADMIN accounts can do everything. A STAFF account carries an explicit list
of permissions. A STAFF account whose list was never set (NULL -- every staff
account created before permissions existed) keeps exactly the access staff
always had: the read-only admin screens, and nothing new.
"""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    DASHBOARD_VIEW = "dashboard.view"
    ORDERS_VIEW = "orders.view"
    ORDERS_MANAGE = "orders.manage"
    CATALOGUE_VIEW = "catalogue.view"
    CATALOGUE_MANAGE = "catalogue.manage"
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_MANAGE = "customers.manage"
    COUPONS_VIEW = "coupons.view"
    COUPONS_MANAGE = "coupons.manage"
    REVIEWS_VIEW = "reviews.view"
    REVIEWS_MANAGE = "reviews.manage"
    PAYMENTS_VIEW = "payments.view"
    PAYMENTS_MANAGE = "payments.manage"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"
    REPORTS_VIEW = "reports.view"
    CMS_VIEW = "cms.view"
    CMS_MANAGE = "cms.manage"
    CMS_PUBLISH = "cms.publish"
    AUDIT_VIEW = "audit.view"


ALL_PERMISSIONS = frozenset(p.value for p in Permission)

# What an unconfigured (legacy) STAFF account can see in the admin menu.
LEGACY_STAFF_PERMISSIONS = frozenset(
    {
        Permission.DASHBOARD_VIEW.value,
        Permission.ORDERS_VIEW.value,
        Permission.CATALOGUE_VIEW.value,
        Permission.COUPONS_VIEW.value,
        Permission.REVIEWS_VIEW.value,
        Permission.PAYMENTS_VIEW.value,
        Permission.SETTINGS_VIEW.value,
    }
)

PERMISSION_DESCRIPTIONS = {
    Permission.DASHBOARD_VIEW: "See the dashboard",
    Permission.ORDERS_VIEW: "See orders, tracking and invoices",
    Permission.ORDERS_MANAGE: "Change order status, shipment, address and tracking",
    Permission.CATALOGUE_VIEW: "See products, categories and stock",
    Permission.CATALOGUE_MANAGE: "Add and edit products, categories, images and stock",
    Permission.CUSTOMERS_VIEW: "See customers and their order history",
    Permission.CUSTOMERS_MANAGE: "Tag customers and add notes",
    Permission.COUPONS_VIEW: "See coupons and offers",
    Permission.COUPONS_MANAGE: "Create and edit coupons and offers",
    Permission.REVIEWS_VIEW: "See reviews and review requests",
    Permission.REVIEWS_MANAGE: "Approve or hide reviews",
    Permission.PAYMENTS_VIEW: "See payments",
    Permission.PAYMENTS_MANAGE: "Confirm advances and record COD remittances",
    Permission.SETTINGS_VIEW: "See shipping, tax, GST, COD and delivery settings",
    Permission.SETTINGS_MANAGE: "Change shipping, tax, GST, COD and delivery settings",
    Permission.REPORTS_VIEW: "See sales, GST, COD and other reports",
    Permission.CMS_VIEW: "See website content",
    Permission.CMS_MANAGE: "Create and edit website content",
    Permission.CMS_PUBLISH: "Publish and unpublish website content",
    Permission.AUDIT_VIEW: "See the activity log",
}


def effective_permissions(role: str, permissions: list[str] | None) -> frozenset[str]:
    if role == "ADMIN":
        return ALL_PERMISSIONS
    if role != "STAFF":
        return frozenset()
    if permissions is None:
        return LEGACY_STAFF_PERMISSIONS
    return frozenset(p for p in permissions if p in ALL_PERMISSIONS)


def has_permission(user, permission: Permission) -> bool:
    """Same rule as `require_permission`, for checks inside an endpoint."""
    if user.role == "ADMIN":
        return True
    return user.role == "STAFF" and permission.value in (user.permissions or [])
