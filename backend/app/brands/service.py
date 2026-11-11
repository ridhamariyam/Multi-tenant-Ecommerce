"""Brand registration, membership and brand-scoped tokens."""

from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole, UserStatus
from app.auth.security import create_access_token, hash_password
from app.brands.constants import BRAND_MANAGER_ROLES, BrandRole, MemberStatus, admin_user_for_role
from app.brands.models import BrandMember
from app.brands.schemas import (
    BrandMembershipRead,
    BrandRead,
    BrandRegister,
    BrandRegistered,
    BrandToken,
    BrandUpdate,
    MemberCreate,
    MemberRead,
    MemberUpdate,
)
from app.core.config import get_settings
from app.core.error_codes import BrandErrorCode, MerchantErrorCode
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.slugs import slugify, with_suffix
from app.merchants.models import MerchantAccount
from app.subscriptions.service import SubscriptionService, start_free
from app.stores.models import Store
from app.stores.service import check_subdomain_available, store_read
from app.tenants.models import Tenant
from app.tenants.provisioning import ensure_tenant_defaults
from app.users.models import User

SLUG_MAX_LENGTH = 63


async def unusable_password_hash() -> str:
    """Satisfies users.password_matches_role for staff who never use a password.

    Members sign in on the platform; nobody knows this secret, so the
    per-store password login can never succeed for their brand user row.
    """
    return await hash_password(secrets.token_urlsafe(48))


def issue_brand_token(membership: BrandMember, user: User) -> BrandToken:
    minutes = get_settings().brand_token_expire_minutes
    return BrandToken(
        access_token=create_access_token(
            user_id=user.id,
            tenant_id=membership.tenant_id,
            role=user.role,
            membership_id=membership.id,
            expires_minutes=minutes,
        ),
        expires_in=minutes * 60,
        brand_id=membership.tenant_id,
        membership_id=membership.id,
        role=membership.role,
    )


def member_read(member: BrandMember, account: MerchantAccount) -> MemberRead:
    return MemberRead(
        id=member.id,
        account_id=account.id,
        email=account.email,
        name=account.name,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


class BrandService:
    def __init__(self, session: AsyncSession, account: MerchantAccount) -> None:
        self.session = session
        self.account = account

    # -- registration ---------------------------------------------------

    async def register(self, data: BrandRegister) -> BrandRegistered:
        slug = data.slug or await self._free_slug(slugify(data.name, SLUG_MAX_LENGTH, "brand"))
        if await self.session.scalar(select(Tenant.id).where(Tenant.slug == slug)) is not None:
            raise ConflictError("That brand handle is taken", error_code=BrandErrorCode.SLUG_TAKEN)
        subdomain = data.subdomain or slug
        await check_subdomain_available(self.session, subdomain)

        # One transaction: the brand, its owner's membership and admin row,
        # its store and its default settings exist together or not at all.
        try:
            tenant = Tenant(
                name=data.name.strip(),
                slug=slug,
                currency=data.currency,
                description=data.description,
                contact_email=data.contact_email,
                phone=data.phone,
                owner_account_id=self.account.id,
                is_active=True,
            )
            self.session.add(tenant)
            await self.session.flush()

            user = await self._brand_user(tenant.id, BrandRole.OWNER.value)
            membership = BrandMember(
                tenant_id=tenant.id,
                account_id=self.account.id,
                user_id=user.id,
                role=BrandRole.OWNER.value,
            )
            store = Store(tenant_id=tenant.id, name=tenant.name, subdomain=subdomain)
            self.session.add_all([membership, store])
            await self.session.flush()
            await ensure_tenant_defaults(self.session, tenant)
            await start_free(self.session, tenant.id)
            await self.session.commit()
            for row in (tenant, store, membership):
                await self.session.refresh(row)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "That brand handle or address is taken", error_code=BrandErrorCode.SLUG_TAKEN
            ) from exc

        return BrandRegistered(
            brand=BrandRead.model_validate(tenant),
            store=store_read(store),
            token=issue_brand_token(membership, user),
        )

    async def _free_slug(self, base: str) -> str:
        candidate, n = base, 1
        while (
            await self.session.scalar(select(Tenant.id).where(Tenant.slug == candidate))
            is not None
            or await self.session.scalar(select(Store.id).where(Store.subdomain == candidate))
            is not None
        ):
            n += 1
            candidate = with_suffix(base, n, SLUG_MAX_LENGTH)
        return candidate

    async def _brand_user(
        self, tenant_id: UUID, role: str, account: MerchantAccount | None = None
    ) -> User:
        """The brand's ADMIN/STAFF row for this account, with the role's access.

        A staff login with the same email made before memberships existed (on
        the staff screen) is adopted rather than duplicated; the unique index
        on staff emails would refuse a second row anyway.
        """
        account = account or self.account
        user_role, permissions = admin_user_for_role(role)
        user = await self.session.scalar(
            select(User).where(
                User.tenant_id == tenant_id,
                User.email == account.email,
                User.role.in_((UserRole.ADMIN.value, UserRole.STAFF.value)),
            )
        )
        if user is None:
            return await self._create_user(tenant_id, user_role, permissions, account=account)
        if await self.session.scalar(
            select(BrandMember.id).where(
                BrandMember.tenant_id == tenant_id, BrandMember.user_id == user.id
            )
        ) is not None:
            raise ConflictError("Already a member", error_code=BrandErrorCode.ALREADY_MEMBER)
        self._apply_role(user, user_role, permissions)
        user.status = UserStatus.ACTIVE.value
        return user

    # -- memberships ----------------------------------------------------

    async def memberships(self) -> list[BrandMembershipRead]:
        rows = (
            await self.session.execute(
                select(BrandMember, Tenant, Store)
                .join(Tenant, Tenant.id == BrandMember.tenant_id)
                .outerjoin(Store, Store.tenant_id == Tenant.id)
                .where(
                    BrandMember.account_id == self.account.id,
                    BrandMember.status == MemberStatus.ACTIVE.value,
                )
                .order_by(Tenant.name)
            )
        ).all()
        return [
            BrandMembershipRead(
                membership_id=member.id,
                role=member.role,
                brand=BrandRead.model_validate(tenant),
                store=store_read(store) if store else None,
            )
            for member, tenant, store in rows
        ]

    async def membership(self, brand_id: UUID) -> tuple[BrandMember, Tenant]:
        """This account's active membership of the brand.

        A brand the account is not a member of is reported as not found, the
        same as one that does not exist, so ids cannot be probed.
        """
        row = (
            await self.session.execute(
                select(BrandMember, Tenant)
                .join(Tenant, Tenant.id == BrandMember.tenant_id)
                .where(
                    BrandMember.tenant_id == brand_id,
                    BrandMember.account_id == self.account.id,
                    BrandMember.status == MemberStatus.ACTIVE.value,
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Brand not found", error_code=BrandErrorCode.NOT_FOUND)
        return row[0], row[1]

    async def managed(self, brand_id: UUID) -> tuple[BrandMember, Tenant]:
        member, tenant = await self.membership(brand_id)
        if member.role not in BRAND_MANAGER_ROLES:
            raise PermissionDeniedError(
                "Only the brand's owner or admins can do this",
                error_code=BrandErrorCode.ROLE_REQUIRED,
            )
        return member, tenant

    async def switch(self, brand_id: UUID) -> BrandToken:
        member, tenant = await self.membership(brand_id)
        if not tenant.is_active:
            raise PermissionDeniedError("This brand is suspended", error_code=BrandErrorCode.SUSPENDED)
        user = await self.session.get(User, member.user_id)
        if user is None or not user.is_active:
            raise NotFoundError("Brand not found", error_code=BrandErrorCode.NOT_FOUND)
        return issue_brand_token(member, user)

    async def get(self, brand_id: UUID) -> Tenant:
        return (await self.membership(brand_id))[1]

    async def update(self, brand_id: UUID, data: BrandUpdate) -> Tenant:
        _, tenant = await self.managed(brand_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(tenant, field, value)
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    # -- members ----------------------------------------------------------

    async def list_members(self, brand_id: UUID) -> list[MemberRead]:
        await self.membership(brand_id)
        rows = (
            await self.session.execute(
                select(BrandMember, MerchantAccount)
                .join(MerchantAccount, MerchantAccount.id == BrandMember.account_id)
                .where(BrandMember.tenant_id == brand_id)
                .order_by(BrandMember.created_at)
            )
        ).all()
        return [member_read(member, account) for member, account in rows]

    async def add_member(self, brand_id: UUID, data: MemberCreate) -> MemberRead:
        await self.managed(brand_id)
        invitee = await self.session.scalar(
            select(MerchantAccount).where(MerchantAccount.email == data.email)
        )
        if invitee is None:
            raise NotFoundError(
                "No merchant account uses that email. Ask them to sign up first.",
                error_code=MerchantErrorCode.NOT_FOUND,
            )
        existing = await self.session.scalar(
            select(BrandMember).where(
                BrandMember.tenant_id == brand_id, BrandMember.account_id == invitee.id
            )
        )
        if existing is not None and existing.status == MemberStatus.ACTIVE.value:
            raise ConflictError("Already a member", error_code=BrandErrorCode.ALREADY_MEMBER)
        plans = SubscriptionService(self.session, brand_id)
        await plans.check_limit("staff_limit", (await plans.usage())["staff"])

        user_role, permissions = admin_user_for_role(data.role)
        if existing is not None:
            # Re-adding a removed member reactivates their brand user.
            existing.status = MemberStatus.ACTIVE.value
            existing.role = data.role
            member = existing
            user = await self.session.get(User, existing.user_id)
            self._apply_role(user, user_role, permissions)
            user.status = UserStatus.ACTIVE.value
        else:
            user = await self._brand_user(brand_id, data.role, account=invitee)
            member = BrandMember(
                tenant_id=brand_id, account_id=invitee.id, user_id=user.id, role=data.role
            )
            self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member_read(member, invitee)

    async def update_member(self, brand_id: UUID, member_id: UUID, data: MemberUpdate) -> MemberRead:
        await self.managed(brand_id)
        row = (
            await self.session.execute(
                select(BrandMember, MerchantAccount)
                .join(MerchantAccount, MerchantAccount.id == BrandMember.account_id)
                .where(BrandMember.id == member_id, BrandMember.tenant_id == brand_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Member not found", error_code=BrandErrorCode.MEMBER_NOT_FOUND)
        member, account = row
        if member.role == BrandRole.OWNER.value:
            raise PermissionDeniedError(
                "The owner's membership cannot be changed",
                error_code=BrandErrorCode.OWNER_IMMUTABLE,
            )
        user = await self.session.get(User, member.user_id)
        if data.role is not None:
            member.role = data.role
            self._apply_role(user, *admin_user_for_role(data.role))
        if data.status is not None:
            member.status = data.status
            user.status = (
                UserStatus.ACTIVE.value
                if data.status == MemberStatus.ACTIVE.value
                else UserStatus.INACTIVE.value
            )
        await self.session.commit()
        await self.session.refresh(member)
        return member_read(member, account)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _apply_role(user: User, role: str, permissions: list[str] | None) -> None:
        user.role = role
        user.permissions = permissions

    async def _create_user(
        self,
        tenant_id: UUID,
        role: str,
        permissions: list[str] | None,
        *,
        account: MerchantAccount | None = None,
    ) -> User:
        account = account or self.account
        user = User(
            tenant_id=tenant_id,
            email=account.email,
            name=account.name,
            phone=None,
            role=role,
            permissions=permissions,
            status=UserStatus.ACTIVE.value,
            password_hash=await unusable_password_hash(),
            is_verified=True,
        )
        self.session.add(user)
        await self.session.flush()
        return user
