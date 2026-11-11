"""Every route of API v1, in the order FastAPI matches them."""

from __future__ import annotations

from fastapi import APIRouter

from app.addresses import router as addresses
from app.audit import router as audit
from app.auth import router as auth
from app.brands import platform as brands_platform
from app.brands import platform_system
from app.brands import router as brands
from app.cart import router as cart
from app.catalogue import router as catalogue
from app.cms import router as cms
from app.cod import router as cod
from app.coupons import router as coupons
from app.customers import router as customers
from app.dashboard import router as dashboard
from app.integrations import router as integrations
from app.tenants import tls as tenant_tls
from app.merchants import router as merchants
from app.orders import router as orders
from app.payments import gateway_router as payment_gateway
from app.subscriptions import router as billing_routes
from app.marketing import router as marketing
from app.ai import router as ai_studio
from app.looks import router as looks
from app.payments import router as payments
from app.pricing import router as pricing
from app.ratings import router as ratings
from app.reports import router as reports
from app.returns import router as returns
from app.search_filter import router as search_filter
from app.shipments import router as shipments
from app.stores import router as stores
from app.stores import storefront as stores_storefront
from app.users import router as users
from app.virtual_models import router as virtual_models
from app.wishlist import router as wishlist

api_router = APIRouter()

for router in (
    auth.router,
    auth.admin_router,
    auth.staff_router,
    merchants.router,
    brands.router,
    brands_platform.router,
    platform_system.router,
    stores.router,
    stores_storefront.router,
    virtual_models.router,
    virtual_models.admin_router,
    users.admin_router,
    audit.router,
    customers.router,
    catalogue.router,
    catalogue.storefront_router,
    cart.router,
    addresses.router,
    orders.checkout_router,
    orders.router,
    orders.admin_router,
    orders.tracking_router,
    shipments.router,
    shipments.settings_router,
    shipments.webhook_router,
    wishlist.router,
    payments.router,
    payment_gateway.router,
    billing_routes.router,
    marketing.router,
    marketing.public_router,
    ai_studio.router,
    ai_studio.webhook_router,
    looks.router,
    looks.public_router,
    payments.admin_router,
    pricing.shipping_router,
    pricing.tax_router,
    pricing.pincode_router,
    pricing.delivery_router,
    pricing.gst_router,
    pricing.storefront_tax_router,
    cod.router,
    coupons.router,
    coupons.admin_router,
    ratings.router,
    ratings.admin_router,
    search_filter.router,
    dashboard.router,
    reports.router,
    returns.router,
    integrations.router,
    cms.router,
    cms.storefront_router,
    tenant_tls.router,
):
    api_router.include_router(router)
