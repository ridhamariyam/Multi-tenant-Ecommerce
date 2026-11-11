"""The one place a GST rate is chosen and a basket's tax is calculated.

Checkout preview, order placement (and so the payment amount) and the admin
product review all go through `TaxEngine`, so they cannot disagree. Rates and
prices come from the database only; nothing the shopper sends is trusted.

For each line, strongest first:

1. an ACTIVE, CA-confirmed TaxRateConfiguration for the product, then its category;
2. a gst_rate typed on the product, then its category (manual, unverified);
3. a system GstDefaultRule for the product's classification, value per piece
   and date -- the classification comes from its HSN code, or else from the
   store's assumed classification;
4. the fallback rate, flagged for review.

The arithmetic itself (discount spread, inclusive extraction, CGST/SGST/IGST,
rounding) stays in app.pricing.gst.compute_tax.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import TaxErrorCode
from app.core.exceptions import ConflictError
from app.core.money import ZERO
from app.orders.constants import GstType
from app.pricing.constants import (
    DEFAULT_SHIPPING_SAC_CODE,
    DEFAULT_TAX_CLASSIFICATION,
    GST_TIMEZONE,
    PERCENT,
    TaxSource,
    TaxVerification,
)
from app.pricing.gst import TaxableLine, TaxResult, _spread, compute_tax, supply_type
from app.pricing.models import GstDefaultRule, GstSettings, TaxRateConfiguration, TaxSettings


def tax_date() -> date:
    """Today in India, the date GST rules take effect by."""
    return datetime.now(ZoneInfo(GST_TIMEZONE)).date()


@dataclass
class TaxProfile:
    """A tenant's tax configuration, with platform defaults for anything unset."""

    enabled: bool = True
    prices_include_gst: bool = False
    seller_state_code: str | None = None
    default_classification: str | None = DEFAULT_TAX_CLASSIFICATION
    fallback_rate: Decimal | None = None
    defaults_reviewed: bool = False
    # Set only once the shipping/COD rate is active and CA-confirmed.
    charges_rate: Decimal | None = None
    shipping_sac_code: str = DEFAULT_SHIPPING_SAC_CODE
    settings: GstSettings | None = None

    @classmethod
    def of(cls, gst: GstSettings | None, tax: TaxSettings | None) -> TaxProfile:
        confirmed = tax is not None and tax.is_active and tax.confirmed_by_ca
        charges_rate = tax.tax_percentage if confirmed else None
        if gst is None:
            return cls(charges_rate=charges_rate)
        return cls(
            enabled=gst.gst_enabled and gst.registration_status != "NOT_REGISTERED",
            prices_include_gst=gst.prices_include_gst,
            seller_state_code=gst.state_code,
            default_classification=gst.default_classification,
            fallback_rate=gst.fallback_gst_rate,
            defaults_reviewed=gst.defaults_reviewed_at is not None,
            charges_rate=charges_rate,
            shipping_sac_code=gst.shipping_sac_code or DEFAULT_SHIPPING_SAC_CODE,
            settings=gst,
        )


@dataclass
class TaxLineInput:
    """One basket line at its trusted database price, with the catalogue's GST fields."""

    key: object
    product_id: UUID
    category_id: UUID | None
    quantity: int
    amount: Decimal  # unit price x quantity, before any discount
    product_hsn: str | None = None
    product_rate: Decimal | None = None
    category_hsn: str | None = None
    category_rate: Decimal | None = None


@dataclass
class RateResolution:
    rate: Decimal
    source: str
    verification: str
    hsn_code: str | None = None
    classification: str | None = None
    rule: GstDefaultRule | None = None
    configuration_id: UUID | None = None
    reason: str = ""

    @property
    def rule_code(self) -> str | None:
        return self.rule.code if self.rule is not None else None

    @property
    def needs_review(self) -> bool:
        return self.verification in {
            TaxVerification.AWAITING_VERIFICATION,
            TaxVerification.NEEDS_REVIEW,
        }


@dataclass
class TaxCalculation:
    result: TaxResult
    resolutions: dict[object, RateResolution] = field(default_factory=dict)
    charges_rate: Decimal = ZERO
    charges_verified: bool = True

    @property
    def review_required(self) -> bool:
        return not self.charges_verified or any(
            resolution.needs_review for resolution in self.resolutions.values()
        )


def _in_band(rule: GstDefaultRule, value: Decimal) -> bool:
    above_min = rule.min_unit_value is None or value > rule.min_unit_value
    below_max = rule.max_unit_value is None or value <= rule.max_unit_value
    return above_min and below_max


def select_band(rules: list[GstDefaultRule], unit_price: Decimal, *, inclusive: bool):
    """The rule whose per-piece value band holds this price, or None.

    A tax-exclusive price is the value itself. A tax-inclusive price holds the
    tax, so each band is tested against the value left once its own rate is
    taken out (Rs 2,600 incl. is 2,476.19 at 5% -- inside the 5% band). Where
    no band is consistent, the highest-rate band the price reaches is used, so
    tax is not under-collected.
    """
    ordered = sorted(rules, key=lambda rule: rule.min_unit_value or Decimal("-1"))
    for rule in ordered:
        value = unit_price * PERCENT / (PERCENT + rule.gst_rate) if inclusive else unit_price
        if _in_band(rule, value):
            return rule
    reached = [
        rule for rule in ordered if rule.min_unit_value is None or unit_price > rule.min_unit_value
    ]
    return max(reached, key=lambda rule: rule.gst_rate) if reached else None


class TaxEngine:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def profile(self, *, for_update: bool = False) -> TaxProfile:
        gst_query = select(GstSettings).where(GstSettings.tenant_id == self.tenant_id)
        tax_query = select(TaxSettings).where(TaxSettings.tenant_id == self.tenant_id)
        if for_update:
            gst_query = gst_query.with_for_update()
            tax_query = tax_query.with_for_update()
        return TaxProfile.of(
            await self.session.scalar(gst_query), await self.session.scalar(tax_query)
        )

    async def rules_on(self, on: date) -> list[GstDefaultRule]:
        return list(
            (
                await self.session.scalars(
                    select(GstDefaultRule).where(
                        GstDefaultRule.effective_from <= on,
                        or_(
                            GstDefaultRule.effective_to.is_(None),
                            GstDefaultRule.effective_to >= on,
                        ),
                    )
                )
            ).all()
        )

    async def approved_for(
        self, lines: list[TaxLineInput], on: date
    ) -> tuple[dict[UUID, TaxRateConfiguration], dict[UUID, TaxRateConfiguration]]:
        product_ids = {line.product_id for line in lines}
        category_ids = {line.category_id for line in lines if line.category_id is not None}
        targets = []
        if product_ids:
            targets.append(TaxRateConfiguration.product_id.in_(product_ids))
        if category_ids:
            targets.append(TaxRateConfiguration.category_id.in_(category_ids))
        if not targets:
            return {}, {}
        mappings = (
            await self.session.scalars(
                select(TaxRateConfiguration)
                .where(
                    TaxRateConfiguration.tenant_id == self.tenant_id,
                    TaxRateConfiguration.status == "ACTIVE",
                    TaxRateConfiguration.ca_confirmed.is_(True),
                    TaxRateConfiguration.effective_from <= on,
                    or_(*targets),
                )
                .order_by(
                    TaxRateConfiguration.effective_from.desc(),
                    TaxRateConfiguration.created_at.desc(),
                )
            )
        ).all()
        by_product: dict[UUID, TaxRateConfiguration] = {}
        by_category: dict[UUID, TaxRateConfiguration] = {}
        for mapping in mappings:
            if mapping.product_id is not None:
                by_product.setdefault(mapping.product_id, mapping)
            elif mapping.category_id is not None:
                by_category.setdefault(mapping.category_id, mapping)
        return by_product, by_category

    def resolve(
        self,
        line: TaxLineInput,
        unit_value: Decimal,
        *,
        profile: TaxProfile,
        rules: list[GstDefaultRule],
        approved: tuple[dict, dict],
    ) -> RateResolution:
        """Choose one line's rate. `unit_value` is the price per piece after discount."""
        by_product, by_category = approved
        hsn = line.product_hsn or line.category_hsn

        if not profile.enabled:
            return RateResolution(
                ZERO, TaxSource.DISABLED, TaxVerification.NOT_APPLICABLE, hsn_code=hsn,
                reason="GST is switched off for this store",
            )

        mapping = by_product.get(line.product_id) or by_category.get(line.category_id)
        if mapping is not None:
            return RateResolution(
                mapping.gst_rate, TaxSource.APPROVED_OVERRIDE, TaxVerification.VERIFIED,
                hsn_code=mapping.hsn_code, configuration_id=mapping.id,
                reason="CA-confirmed product/category rate",
            )

        manual = line.product_rate if line.product_rate is not None else line.category_rate
        if manual is not None:
            return RateResolution(
                manual, TaxSource.MANUAL, TaxVerification.AWAITING_VERIFICATION, hsn_code=hsn,
                reason="Rate entered on the product or category, not yet CA-confirmed",
            )

        classified = [rule for rule in rules if not rule.is_fallback]
        if hsn:
            candidates = [
                rule for rule in classified
                if any(hsn.startswith(prefix) for prefix in rule.hsn_prefixes)
            ]
            assumed = False
            reason = f"HSN {hsn} is not covered by a system default rule"
        elif profile.default_classification:
            candidates = [
                rule for rule in classified
                if rule.classification == profile.default_classification
            ]
            assumed = True
            reason = f"No HSN code; no {profile.default_classification} rule in force"
        else:
            candidates = []
            assumed = False
            reason = "No HSN code and no assumed classification"

        rule = select_band(candidates, unit_value, inclusive=profile.prices_include_gst)
        if rule is not None:
            verified = profile.defaults_reviewed
            return RateResolution(
                rule.gst_rate, TaxSource.SYSTEM_DEFAULT,
                TaxVerification.VERIFIED if verified else TaxVerification.AWAITING_VERIFICATION,
                hsn_code=hsn, classification=rule.classification, rule=rule,
                reason=(
                    f"System default ({rule.description})"
                    + ("; classification assumed for the store" if assumed else "")
                ),
            )
        return self._fallback(rules, profile, hsn, reason)

    @staticmethod
    def _fallback(
        rules: list[GstDefaultRule], profile: TaxProfile, hsn: str | None, reason: str
    ) -> RateResolution:
        system = next((rule for rule in rules if rule.is_fallback), None)
        if profile.fallback_rate is not None:
            rate, rule = profile.fallback_rate, None
        elif system is not None:
            rate, rule = system.gst_rate, system
        else:
            raise ConflictError(
                "No GST rate could be determined and no fallback rate is configured.",
                error_code=TaxErrorCode.RATE_NOT_FOUND,
            )
        return RateResolution(
            rate, TaxSource.FALLBACK, TaxVerification.NEEDS_REVIEW, hsn_code=hsn, rule=rule,
            reason=f"{reason}; fallback rate applied",
        )

    async def calculate(
        self,
        lines: list[TaxLineInput],
        *,
        discount: Decimal,
        charges: Decimal,
        buyer_state: str | None,
        profile: TaxProfile,
        on: date | None = None,
    ) -> TaxCalculation:
        """Tax for a basket: each line at its resolved rate, charges at the charges rate.

        Value thresholds are per piece and after the discount, which is spread
        over the lines exactly as compute_tax spreads it.
        """
        on = on or tax_date()
        rules = await self.rules_on(on)
        approved = await self.approved_for(lines, on) if profile.enabled else ({}, {})

        shares = _spread(discount, [line.amount for line in lines])
        resolutions: dict[object, RateResolution] = {}
        for line, share in zip(lines, shares, strict=True):
            unit_value = (line.amount - share) / line.quantity
            resolutions[line.key] = self.resolve(
                line, unit_value, profile=profile, rules=rules, approved=approved
            )

        # Delivery/COD charges follow the goods (composite supply) at the highest
        # goods rate, until the store confirms a rate of its own for them.
        if profile.charges_rate is not None:
            charges_rate, charges_verified = profile.charges_rate, True
        else:
            charges_rate = max((r.rate for r in resolutions.values()), default=ZERO)
            charges_verified = charges <= ZERO or not profile.enabled

        gst_type: GstType | None = supply_type(profile.seller_state_code, buyer_state)
        result = compute_tax(
            [
                TaxableLine(
                    key=line.key,
                    amount=line.amount,
                    rate=resolutions[line.key].rate,
                    hsn_code=resolutions[line.key].hsn_code,
                    prices_include_tax=profile.prices_include_gst,
                )
                for line in lines
            ],
            discount=discount,
            charges=charges,
            default_rate=charges_rate if profile.enabled else ZERO,
            active=profile.enabled,
            gst_type=gst_type,
        )
        return TaxCalculation(
            result=result,
            resolutions=resolutions,
            charges_rate=result.charges_rate,
            charges_verified=charges_verified,
        )
