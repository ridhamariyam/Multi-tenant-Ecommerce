from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.models import Category, Product, ProductVariant
from app.catalogue.prices import effective_price
from app.core.database import conflict_on_integrity_error
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.money import ZERO, money
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.pricing.constants import (
    DEFAULT_MAX_DELIVERY_DAYS,
    DEFAULT_MIN_DELIVERY_DAYS,
    TaxSource,
    TaxVerification,
)
from app.pricing.gst import STATE_CODES, state_code_for
from app.pricing.models import (
    GstDefaultRule,
    GstSettings,
    PincodeRule,
    ShippingSettings,
    TaxRateConfiguration,
    TaxSettings,
)
from app.pricing.repository import (
    GstSettingsRepository,
    PincodeRuleRepository,
    ShippingSettingsRepository,
    TaxSettingsRepository,
)
from app.pricing.schemas import (
    GstDefaultRuleRead,
    GstDefaultsRead,
    GstSettingsUpdate,
    PincodeRuleWrite,
    ShippingSettingsUpdate,
    TaxRateConfigurationWrite,
    TaxSettingsUpdate,
)
from app.pricing.tax_engine import TaxEngine, TaxLineInput, TaxProfile, tax_date

SAVE_FAILED = "Unable to save the settings, please try again"


class ShippingService:
    """One flat delivery charge per tenant, optionally free above a threshold."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.settings = ShippingSettingsRepository(session, tenant_id)

    async def get_settings(self) -> ShippingSettings | None:
        return await self.settings.get_for_tenant()

    async def update_settings(self, data: ShippingSettingsUpdate) -> ShippingSettings:
        """Write the tenant's one row, creating it the first time."""
        settings = await self.get_settings()

        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            if settings is None:
                settings = ShippingSettings(
                    shipping_amount=data.shipping_amount,
                    free_shipping_minimum=data.free_shipping_minimum,
                    is_active=data.is_active,
                    min_delivery_days=data.min_delivery_days,
                    max_delivery_days=data.max_delivery_days,
                    restrict_to_listed_pincodes=data.restrict_to_listed_pincodes,
                )
                await self.settings.add(settings)
            else:
                settings.shipping_amount = data.shipping_amount
                settings.free_shipping_minimum = data.free_shipping_minimum
                settings.is_active = data.is_active
                settings.min_delivery_days = data.min_delivery_days
                settings.max_delivery_days = data.max_delivery_days
                settings.restrict_to_listed_pincodes = data.restrict_to_listed_pincodes

            await self.session.commit()

        return settings

    async def calculate(self, subtotal: Decimal, rule: PincodeRule | None = None) -> Decimal:
        """What this basket costs to deliver; a pincode rule may replace the flat charge."""
        settings = await self.get_settings()

        if settings is None or not settings.is_active:
            return ZERO

        minimum = settings.free_shipping_minimum
        if minimum is not None and subtotal >= minimum:
            return ZERO

        if rule is not None and rule.shipping_amount is not None:
            return money(rule.shipping_amount)
        return money(settings.shipping_amount)


class TaxService:
    """CA-confirmed rate reserved for shipping and COD charge classifications."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.settings = TaxSettingsRepository(session, tenant_id)

    async def get_settings(self) -> TaxSettings | None:
        return await self.settings.get_for_tenant()

    async def update_settings(self, data: TaxSettingsUpdate) -> TaxSettings:
        """Write the tenant's one row, creating it the first time."""
        settings = await self.session.scalar(
            select(TaxSettings).where(TaxSettings.tenant_id == self.tenant_id).with_for_update()
        )

        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            if settings is None:
                settings = TaxSettings(
                    tax_percentage=data.tax_percentage, is_active=False, confirmed_by_ca=False
                )
                await self.settings.add(settings)
            else:
                settings.tax_percentage = data.tax_percentage
                settings.is_active = False
                settings.confirmed_by_ca = False

            await self.session.commit()

        return settings

    async def confirm_settings(self, *, ca_confirmed: bool) -> TaxSettings:
        settings = await self.session.scalar(
            select(TaxSettings).where(TaxSettings.tenant_id == self.tenant_id).with_for_update()
        )
        if settings is None:
            raise NotFoundError("Save the shipping/COD tax rate before confirmation")
        if not ca_confirmed:
            raise ValidationError("Rate activation requires explicit CA/accountant confirmation")
        settings.confirmed_by_ca = True
        settings.is_active = True
        await self.session.commit()
        await self.session.refresh(settings)
        return settings


@dataclass
class DeliveryQuote:
    """Whether, how fast and for how much a pincode is delivered to."""

    pincode: str
    serviceable: bool
    rule: PincodeRule | None
    min_days: int | None = None
    max_days: int | None = None
    earliest: date | None = None
    latest: date | None = None
    shipping_amount: Decimal | None = None
    free_shipping_minimum: Decimal | None = None

    @property
    def cod_allowed_here(self) -> bool:
        return self.serviceable and (self.rule is None or self.rule.cod_available)


def today() -> date:
    return datetime.now(timezone.utc).date()


class DeliveryService:
    """Pincode serviceability, delivery estimates and delivery cost."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.rules = PincodeRuleRepository(session, tenant_id)
        self.shipping = ShippingService(session, tenant_id)

    async def quote(self, pincode: str, subtotal: Decimal) -> DeliveryQuote:
        code = pincode.strip()
        settings = await self.shipping.get_settings()
        rule = await self.rules.get_by_pincode(code)

        if rule is not None:
            serviceable = rule.is_serviceable
        else:
            serviceable = not (settings is not None and settings.restrict_to_listed_pincodes)

        if not serviceable:
            return DeliveryQuote(pincode=code, serviceable=False, rule=rule)

        if rule is not None and rule.min_delivery_days is not None:
            min_days, max_days = rule.min_delivery_days, rule.max_delivery_days
        elif settings is not None:
            min_days, max_days = settings.min_delivery_days, settings.max_delivery_days
        else:
            min_days, max_days = DEFAULT_MIN_DELIVERY_DAYS, DEFAULT_MAX_DELIVERY_DAYS

        start = today()
        return DeliveryQuote(
            pincode=code,
            serviceable=True,
            rule=rule,
            min_days=min_days,
            max_days=max_days,
            earliest=start + timedelta(days=min_days),
            latest=start + timedelta(days=max_days),
            shipping_amount=await self.shipping.calculate(subtotal, rule),
            free_shipping_minimum=(
                settings.free_shipping_minimum if settings and settings.is_active else None
            ),
        )


class PincodeService:
    """Admin management of per-pincode delivery rules."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.rules = PincodeRuleRepository(session, tenant_id)

    async def list(self, params, *, search=None, is_serviceable=None):
        stmt = self.rules.list_select(search=search, is_serviceable=is_serviceable)
        rows, total = await self.rules.paginate(stmt, params)
        return list(rows), total

    async def get(self, pincode: str) -> PincodeRule:
        rule = await self.rules.get_by_pincode(pincode)
        if rule is None:
            raise NotFoundError("No delivery rule for this pincode")
        return rule

    async def _write(self, pincode: str, data: PincodeRuleWrite) -> PincodeRule:
        rule = await self.rules.get_by_pincode(pincode)
        values = data.model_dump()
        if rule is None:
            rule = await self.rules.add(PincodeRule(pincode=pincode, **values))
        else:
            for field, value in values.items():
                setattr(rule, field, value)
        return rule

    async def upsert(self, pincode: str, data: PincodeRuleWrite) -> PincodeRule:
        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            rule = await self._write(pincode, data)
            await self.session.commit()
        return rule

    async def bulk_upsert(self, items) -> int:
        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            for item in items:
                rule = PincodeRuleWrite(**item.model_dump(exclude={"pincode"}))
                await self._write(item.pincode, rule)
            await self.session.commit()
        return len(items)

    async def delete(self, pincode: str) -> None:
        rule = await self.get(pincode)
        await self.rules.delete(rule)
        await self.session.commit()


class GstService:
    """The seller's GST identity and the GST report."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.settings = GstSettingsRepository(session, tenant_id)

    async def get_settings(self) -> GstSettings | None:
        return await self.settings.get_for_tenant()

    async def update_settings(
        self, data: GstSettingsUpdate, actor_id: UUID | None = None
    ) -> GstSettings:
        state_code = None
        state_name = None
        if data.state:
            state_code = state_code_for(data.state)
            if state_code is None:
                raise ValidationError("Unknown Indian state or GST state code")
            state_name = STATE_CODES[state_code]

        if data.gstin and state_code and data.gstin[:2] != state_code:
            raise ValidationError("The GSTIN does not belong to the selected state")
        if data.gstin and state_code is None:
            state_code = data.gstin[:2]
            state_name = STATE_CODES.get(state_code)
            if state_name is None:
                raise ValidationError("The GSTIN contains an unsupported Indian state code")
        if data.registration_status == "REGISTERED" and not data.gstin:
            raise ValidationError("GSTIN is required when registration status is Registered")
        if data.registration_status != "REGISTERED" and data.gstin:
            raise ValidationError("GSTIN can be saved only when registration status is Registered")

        settings = await self.session.scalar(
            select(GstSettings).where(GstSettings.tenant_id == self.tenant_id).with_for_update()
        )
        values = {
            "gstin": data.gstin,
            "legal_name": data.legal_name,
            "address": data.address,
            "state": state_name,
            "state_code": state_code,
            "invoice_prefix": data.invoice_prefix,
            "shipping_sac_code": data.shipping_sac_code,
            "registration_status": data.registration_status,
            "accounting_software": data.accounting_software,
            "prices_include_gst": data.prices_include_gst,
            "gst_enabled": data.gst_enabled,
            "default_classification": data.default_classification,
            "fallback_gst_rate": data.fallback_gst_rate,
            "configuration_status": "PENDING_CA_CONFIRMATION",
            "updated_by_id": actor_id,
            "confirmed_by_id": None,
            "confirmed_at": None,
        }
        # A review covers the assumptions it was given; changing them reopens it.
        if settings is not None and (
            settings.default_classification != data.default_classification
            or settings.fallback_gst_rate != data.fallback_gst_rate
            or settings.prices_include_gst != data.prices_include_gst
        ):
            values["defaults_reviewed_at"] = None
            values["defaults_reviewed_by_id"] = None
        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            if settings is None:
                settings = await self.settings.add(GstSettings(**values))
            else:
                for field, value in values.items():
                    setattr(settings, field, value)
            await self.session.commit()
        await self.session.refresh(settings)

        return settings

    async def activate_settings(self, *, actor_id: UUID, ca_confirmed: bool) -> GstSettings:
        settings = await self.session.scalar(
            select(GstSettings).where(GstSettings.tenant_id == self.tenant_id).with_for_update()
        )
        if settings is None:
            raise NotFoundError("Save business GST details before activation")
        if not ca_confirmed:
            raise ValidationError("Activation requires explicit CA/accountant confirmation")
        if settings.registration_status in {"UNKNOWN", "APPLICATION_PENDING"}:
            raise ValidationError("Confirm the GST registration status before activation")
        if (
            not settings.legal_name
            or not settings.address
            or settings.state_code not in STATE_CODES
        ):
            raise ValidationError("Legal name, registered address, and state are required")
        if settings.registration_status == "REGISTERED" and not settings.gstin:
            raise ValidationError("GSTIN is required for a registered business")
        settings.configuration_status = "ACTIVE"
        settings.confirmed_by_id = actor_id
        settings.confirmed_at = datetime.now(timezone.utc)
        settings.updated_by_id = actor_id
        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            await self.session.commit()
        # updated_at is set by the database, so the commit leaves it expired.
        await self.session.refresh(settings)
        return settings

    async def defaults(self) -> GstDefaultsRead:
        """The system rules every tenant shares, and this tenant's review of them."""
        settings = await self.get_settings()
        profile = TaxProfile.of(settings, None)
        today = tax_date()
        rules = (
            await self.session.scalars(
                select(GstDefaultRule).order_by(
                    GstDefaultRule.classification,
                    GstDefaultRule.effective_from.desc(),
                    GstDefaultRule.min_unit_value.nulls_first(),
                )
            )
        ).all()
        fallback = next(
            (
                rule for rule in rules
                if rule.is_fallback and rule.effective_from <= today
                and (rule.effective_to is None or rule.effective_to >= today)
            ),
            None,
        )
        return GstDefaultsRead(
            rules=[
                GstDefaultRuleRead(
                    id=rule.id, code=rule.code, classification=rule.classification,
                    description=rule.description, hsn_prefixes=list(rule.hsn_prefixes),
                    min_unit_value=rule.min_unit_value, max_unit_value=rule.max_unit_value,
                    gst_rate=rule.gst_rate, effective_from=rule.effective_from,
                    effective_to=rule.effective_to, is_fallback=rule.is_fallback,
                    verification_status=rule.verification_status, source=rule.source,
                    in_force=rule.effective_from <= today
                    and (rule.effective_to is None or rule.effective_to >= today),
                )
                for rule in rules
            ],
            default_classification=profile.default_classification,
            fallback_gst_rate=profile.fallback_rate,
            system_fallback_rate=fallback.gst_rate if fallback else None,
            reviewed_at=settings.defaults_reviewed_at if settings else None,
            reviewed_by_id=settings.defaults_reviewed_by_id if settings else None,
            status="REVIEWED" if profile.defaults_reviewed else "AWAITING_VERIFICATION",
        )

    async def review_defaults(self, *, actor_id: UUID, reviewed: bool) -> GstDefaultsRead:
        """Record (or withdraw) the store's sign-off on the default rules for itself only."""
        settings = await self.session.scalar(
            select(GstSettings).where(GstSettings.tenant_id == self.tenant_id).with_for_update()
        )
        if settings is None:
            raise NotFoundError("Save the business GST details before reviewing the defaults")
        settings.defaults_reviewed_at = datetime.now(timezone.utc) if reviewed else None
        settings.defaults_reviewed_by_id = actor_id if reviewed else None
        settings.updated_by_id = actor_id
        async with conflict_on_integrity_error(self.session, SAVE_FAILED):
            await self.session.commit()
        return await self.defaults()

    async def product_review(self, *, only_flagged: bool = False) -> list[dict]:
        """How each live product is taxed today at its variants' current prices.

        Uses the same resolver as checkout, before any coupon, so a flagged
        product here is one checkout would also flag.
        """
        engine = TaxEngine(self.session, self.tenant_id)
        profile = await engine.profile()
        on = tax_date()
        rules = await engine.rules_on(on)
        rows = (
            await self.session.execute(
                select(Product, Category)
                .outerjoin(
                    Category,
                    and_(
                        Category.tenant_id == Product.tenant_id,
                        Category.id == Product.category_id,
                    ),
                )
                .where(Product.tenant_id == self.tenant_id, Product.status != "ARCHIVED")
                .order_by(Product.name)
            )
        ).all()
        variants = (
            await self.session.scalars(
                select(ProductVariant).where(
                    ProductVariant.tenant_id == self.tenant_id,
                    ProductVariant.status != "ARCHIVED",
                )
            )
        ).all()
        prices: dict[UUID, list[Decimal]] = {}
        for variant in variants:
            prices.setdefault(variant.product_id, []).append(effective_price(variant))

        inputs = [
            TaxLineInput(
                key=product.id, product_id=product.id, category_id=product.category_id,
                quantity=1, amount=ZERO, product_hsn=product.hsn_code,
                product_rate=product.gst_rate,
                category_hsn=category.hsn_code if category else None,
                category_rate=category.gst_rate if category else None,
            )
            for product, category in rows
        ]
        approved = await engine.approved_for(inputs, on) if profile.enabled else ({}, {})

        review = []
        for (product, category), line in zip(rows, inputs, strict=True):
            resolutions = [
                engine.resolve(line, price, profile=profile, rules=rules, approved=approved)
                for price in sorted(set(prices.get(product.id) or [ZERO]))
            ]
            needs_review = any(resolution.needs_review for resolution in resolutions)
            if only_flagged and not needs_review:
                continue
            # The weakest source and verification across the variants speak for the product.
            worst = max(
                resolutions,
                key=lambda r: (
                    r.verification == TaxVerification.NEEDS_REVIEW,
                    r.verification == TaxVerification.AWAITING_VERIFICATION,
                    r.source == TaxSource.FALLBACK,
                ),
            )
            review.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "category_name": category.name if category else None,
                    "hsn_code": worst.hsn_code,
                    "source": worst.source,
                    "verification": worst.verification,
                    "rule_codes": sorted({r.rule_code for r in resolutions if r.rule_code}),
                    "rates": sorted({r.rate for r in resolutions}),
                    "reason": worst.reason,
                    "needs_review": needs_review,
                }
            )
        return review

    async def list_rate_configurations(self) -> list[dict]:
        rows = (
            await self.session.execute(
                select(TaxRateConfiguration, Product.name, Category.name)
                .outerjoin(Product, Product.id == TaxRateConfiguration.product_id)
                .outerjoin(Category, Category.id == TaxRateConfiguration.category_id)
                .where(TaxRateConfiguration.tenant_id == self.tenant_id)
                .order_by(TaxRateConfiguration.created_at.desc())
            )
        ).all()
        return [
            {
                "id": config.id,
                "product_id": config.product_id,
                "category_id": config.category_id,
                "product_name": product_name,
                "category_name": category_name,
                "hsn_code": config.hsn_code,
                "gst_rate": config.gst_rate,
                "effective_from": config.effective_from,
                "status": config.status,
                "ca_confirmed": config.ca_confirmed,
                "approved_at": config.approved_at,
                "created_by_id": config.created_by_id,
                "approved_by_id": config.approved_by_id,
                "created_at": config.created_at,
            }
            for config, product_name, category_name in rows
        ]

    async def rate_targets(self) -> dict[str, list[dict[str, object]]]:
        products = (
            await self.session.execute(
                select(Product.id, Product.name)
                .where(Product.tenant_id == self.tenant_id, Product.status != "ARCHIVED")
                .order_by(Product.name)
            )
        ).all()
        categories = (
            await self.session.execute(
                select(Category.id, Category.name)
                .where(Category.tenant_id == self.tenant_id, Category.status != "ARCHIVED")
                .order_by(Category.name)
            )
        ).all()
        return {
            "products": [{"id": item_id, "name": name} for item_id, name in products],
            "categories": [{"id": item_id, "name": name} for item_id, name in categories],
        }

    async def create_rate_configuration(
        self, data: TaxRateConfigurationWrite, actor_id: UUID
    ) -> TaxRateConfiguration:
        if data.product_id:
            target = await self.session.scalar(
                select(Product).where(
                    Product.tenant_id == self.tenant_id, Product.id == data.product_id
                )
            )
        else:
            target = await self.session.scalar(
                select(Category).where(
                    Category.tenant_id == self.tenant_id, Category.id == data.category_id
                )
            )
        if target is None:
            raise NotFoundError("The selected product or category was not found")
        config = TaxRateConfiguration(
            product_id=data.product_id,
            category_id=data.category_id,
            hsn_code=data.hsn_code,
            gst_rate=data.gst_rate,
            effective_from=data.effective_from,
            status="PENDING",
            ca_confirmed=False,
            created_by_id=actor_id,
        )
        config.tenant_id = self.tenant_id
        self.session.add(config)
        async with conflict_on_integrity_error(
            self.session,
            "Tax rate configuration conflicts with an existing record",
        ):
            await self.session.commit()
        await self.session.refresh(config)
        return config

    async def approve_rate_configuration(
        self, config_id: UUID, *, actor_id: UUID, ca_confirmed: bool
    ) -> TaxRateConfiguration:
        # Lock tenant settings to serialize competing rate activations.
        gst = await self.session.scalar(
            select(GstSettings).where(GstSettings.tenant_id == self.tenant_id).with_for_update()
        )
        if gst is None or gst.configuration_status != "ACTIVE":
            raise ConflictError("Activate the business GST configuration before approving rates")
        config = await self.session.scalar(
            select(TaxRateConfiguration)
            .where(
                TaxRateConfiguration.tenant_id == self.tenant_id,
                TaxRateConfiguration.id == config_id,
            )
            .with_for_update()
        )
        if config is None:
            raise NotFoundError("Tax rate configuration not found")
        if not ca_confirmed:
            raise ValidationError("Rate activation requires explicit CA/accountant confirmation")
        same_scope = (
            TaxRateConfiguration.product_id == config.product_id
            if config.product_id
            else TaxRateConfiguration.category_id == config.category_id
        )
        conflict = await self.session.scalar(
            select(TaxRateConfiguration.id).where(
                TaxRateConfiguration.tenant_id == self.tenant_id,
                same_scope,
                TaxRateConfiguration.effective_from == config.effective_from,
                TaxRateConfiguration.status == "ACTIVE",
                TaxRateConfiguration.id != config.id,
            )
        )
        if conflict:
            raise ConflictError("An active rate already exists for this target and effective date")
        config.ca_confirmed = True
        config.status = "ACTIVE"
        config.approved_by_id = actor_id
        config.approved_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def report(self, start: date, end: date) -> dict:
        """Taxable value and CGST/SGST/IGST per GST type and rate, for non-cancelled orders."""
        start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        in_range = and_(
            Order.tenant_id == self.tenant_id,
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
            Order.status != OrderStatus.CANCELLED.value,
        )

        # The headline and rows must use the same order snapshots. Item-only sums
        # omit shipping/COD tax and can be zero for orders predating item tax fields.
        orders = (
            await self.session.execute(
                select(
                    Order.id, Order.gst_type, Order.subtotal, Order.discount_amount,
                    Order.shipping_amount, Order.cod_fee, Order.cgst_amount,
                    Order.sgst_amount, Order.igst_amount, Order.tax_amount,
                    Order.tax_included_amount, Order.charges_gst_rate, Order.shipping_sac_code,
                ).where(in_range)
            )
        ).all()
        by_order: dict[UUID, list[Decimal]] = {row[0]: [ZERO, ZERO, ZERO, ZERO] for row in orders}
        buckets: dict[tuple[str | None, Decimal | None, str, str | None], list[Decimal]] = {}

        def add(
            key: tuple[str | None, Decimal | None, str, str | None], amounts: list[Decimal]
        ) -> None:
            bucket = buckets.setdefault(key, [ZERO, ZERO, ZERO, ZERO])
            for index, amount in enumerate(amounts):
                bucket[index] += amount

        items = (
            await self.session.execute(
                select(
                    Order.id, Order.gst_type, OrderItem.gst_rate, OrderItem.hsn_code,
                    OrderItem.subtotal, OrderItem.discount_amount,
                    OrderItem.taxable_amount, OrderItem.tax_amount,
                )
                .join(
                    OrderItem,
                    and_(
                        OrderItem.tenant_id == Order.tenant_id,
                        OrderItem.order_id == Order.id,
                    ),
                )
                .where(in_range)
            )
        ).all()
        for order_id, gst_type, rate, hsn, subtotal, discount, saved_taxable, saved_tax in items:
            taxable = saved_taxable if saved_taxable is not None else subtotal - (discount or ZERO)
            tax = saved_tax or ZERO
            if gst_type == "INTRA_STATE":
                cgst = money(tax / 2)
                amounts = [taxable, cgst, tax - cgst, ZERO]
            elif gst_type == "INTER_STATE":
                amounts = [taxable, ZERO, ZERO, tax]
            else:
                # Preserve legacy tax without assigning an unsupported GST split.
                amounts = [taxable, ZERO, ZERO, ZERO]
            add((gst_type, rate, "ITEMS", hsn), amounts)
            for index, amount in enumerate(amounts):
                by_order[order_id][index] += amount

        totals = [ZERO, ZERO, ZERO, ZERO]
        for (
            order_id, gst_type, subtotal, discount, shipping, cod_fee,
            cgst, sgst, igst, _tax, tax_included, charges_rate, charges_hsn,
        ) in orders:
            order_amounts = [
                subtotal - discount + shipping + cod_fee - tax_included,
                cgst,
                sgst,
                igst,
            ]
            for index, amount in enumerate(order_amounts):
                totals[index] += amount
            remainder = [
                amount - used
                for amount, used in zip(order_amounts, by_order[order_id], strict=True)
            ]
            if any(amount != ZERO for amount in remainder):
                add((gst_type, charges_rate, "CHARGES_AND_ADJUSTMENTS", charges_hsn), remainder)

        by_rate = [
            {
                "component": component,
                "gst_type": gst_type,
                "gst_rate": rate,
                "hsn_code": hsn,
                "taxable_amount": money(amounts[0]),
                "cgst_amount": money(amounts[1]),
                "sgst_amount": money(amounts[2]),
                "igst_amount": money(amounts[3]),
            }
            for (gst_type, rate, component, hsn), amounts in sorted(
                buckets.items(),
                key=lambda entry: (
                    entry[0][0] or "",
                    entry[0][2],
                    entry[0][1] or ZERO,
                    entry[0][3] or "",
                ),
            )
        ]
        taxable, cgst, sgst, igst = totals
        unclassified_tax = sum(
            (row[9] for row in orders if row[1] is None), ZERO
        )
        tax = cgst + sgst + igst + unclassified_tax
        return {
            "start_date": start,
            "end_date": end,
            "order_count": len(orders),
            "taxable_amount": money(taxable),
            "cgst_amount": money(cgst),
            "sgst_amount": money(sgst),
            "igst_amount": money(igst),
            "unclassified_tax_amount": money(unclassified_tax),
            "tax_amount": money(tax),
            "by_rate": by_rate,
        }
