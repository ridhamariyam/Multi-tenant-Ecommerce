"""Signed-off tax configuration for tests that reach checkout.

Checkout refuses to price a basket until the tenant's GST details are ACTIVE,
the shipping/COD rate is CA-confirmed, and every line resolves to an ACTIVE,
CA-confirmed HSN/GST mapping. Tests about ordering, paying or pricing are not
about that approval flow (tests/orders/test_delivery_and_gst.py drives it
through the API), so `sign_off_tax` approves it up front and then keeps a
mapping for every category and product the test writes:

- a product with its own `gst_rate` or `hsn_code` gets a product mapping;
- every category gets a category mapping at its own `gst_rate`, or else at
  the default rate (`TaxSetup.use_default_rate`), 0% until a test sets one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole, UserStatus
from app.auth.security import hash_password
from app.catalogue.models import Category, Product
from app.pricing.models import GstSettings, TaxRateConfiguration, TaxSettings
from app.tenants.models import Tenant
from app.users.models import User

SELLER_GSTIN = "29ABCDE1234F1Z5"
SHIPPING_SAC = "996812"
DEFAULT_HSN = "6109"

# Backdated so a mapping written during the test is already in force.
EFFECTIVE_FROM = date(2000, 1, 1)

_FLUSHED = "tests.tax.flushed"


@dataclass
class TaxSetup:
    session: AsyncSession
    tenant_id: UUID
    approver_id: UUID
    default_rate: Decimal = Decimal("0.00")
    _mappings: dict[UUID, TaxRateConfiguration] = field(default_factory=dict)
    # Categories with no gst_rate of their own follow the default rate.
    _defaulted: set[UUID] = field(default_factory=set)

    async def use_default_rate(self, rate: Decimal | str) -> None:
        self.default_rate = Decimal(rate)
        for category_id in self._defaulted:
            self._mappings[category_id].gst_rate = self.default_rate
        await self.session.commit()

    def map(self, objects: Iterable[object]) -> list[TaxRateConfiguration]:
        """Create or re-rate the mappings for these categories/products."""
        touched = []
        for obj in objects:
            if getattr(obj, "tenant_id", None) != self.tenant_id:
                continue
            if isinstance(obj, Category):
                if obj.gst_rate is None:
                    self._defaulted.add(obj.id)
                else:
                    self._defaulted.discard(obj.id)
                rate = self.default_rate if obj.gst_rate is None else obj.gst_rate
            elif isinstance(obj, Product) and (obj.gst_rate is not None or obj.hsn_code):
                rate = obj.gst_rate if obj.gst_rate is not None else self._category_rate(obj)
            else:
                continue
            mapping = self._mappings.get(obj.id) or self._new_mapping(obj)
            mapping.gst_rate = rate
            mapping.hsn_code = obj.hsn_code or DEFAULT_HSN
            touched.append(mapping)
        return touched

    def _category_rate(self, product: Product) -> Decimal:
        mapping = self._mappings.get(product.category_id)
        return mapping.gst_rate if mapping is not None else self.default_rate

    def _new_mapping(self, obj: Category | Product) -> TaxRateConfiguration:
        is_product = isinstance(obj, Product)
        mapping = TaxRateConfiguration(
            id=uuid4(),
            tenant_id=self.tenant_id,
            product_id=obj.id if is_product else None,
            category_id=None if is_product else obj.id,
            effective_from=EFFECTIVE_FROM,
            status="ACTIVE",
            ca_confirmed=True,
            created_by_id=self.approver_id,
            approved_by_id=self.approver_id,
            approved_at=datetime.now(timezone.utc),
        )
        self._mappings[obj.id] = mapping
        return mapping


async def sign_off_tax(session: AsyncSession, tenant: Tenant) -> TaxSetup:
    """Make `tenant` ready to check out, and keep it ready as the test adds stock."""
    approver = User(
        tenant_id=tenant.id,
        phone="+919999999990",
        email=f"ca-approver@{tenant.slug}.test",
        name="CA approver",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
        # Staff rows must carry a password; nobody signs in as this one.
        password_hash=await hash_password(uuid4().hex),
        is_verified=True,
    )
    session.add(approver)
    await session.flush()

    session.add_all([
        GstSettings(
            tenant_id=tenant.id,
            gstin=SELLER_GSTIN,
            legal_name=f"{tenant.name} Pvt Ltd",
            address="1 MG Road, Bengaluru",
            state="Karnataka",
            state_code=SELLER_GSTIN[:2],
            shipping_sac_code=SHIPPING_SAC,
            registration_status="REGISTERED",
            accounting_software="NONE",
            configuration_status="ACTIVE",
            updated_by_id=approver.id,
            confirmed_by_id=approver.id,
            confirmed_at=datetime.now(timezone.utc),
        ),
        TaxSettings(
            tenant_id=tenant.id,
            tax_percentage=Decimal("0.00"),
            is_active=True,
            confirmed_by_ca=True,
        ),
    ])

    setup = TaxSetup(session=session, tenant_id=tenant.id, approver_id=approver.id)
    categories = (
        await session.scalars(select(Category).where(Category.tenant_id == tenant.id))
    ).all()
    products = (
        await session.scalars(select(Product).where(Product.tenant_id == tenant.id))
    ).all()
    session.add_all(setup.map([*categories, *products]))
    await session.commit()

    def remember(sync_session, _context) -> None:
        # new/dirty still hold the pre-flush state here, and ids are assigned.
        sync_session.info.setdefault(_FLUSHED, []).extend(
            obj
            for obj in [*sync_session.new, *sync_session.dirty]
            if isinstance(obj, (Category, Product))
        )

    def map_flushed(sync_session, _context) -> None:
        # Added after the flush; commit keeps flushing until the session is clean.
        sync_session.add_all(setup.map(sync_session.info.pop(_FLUSHED, [])))

    event.listen(session.sync_session, "after_flush", remember)
    event.listen(session.sync_session, "after_flush_postexec", map_flushed)
    return setup
