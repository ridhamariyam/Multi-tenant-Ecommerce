from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address
from app.audit.service import record_activity
from app.auth.constants import STAFF_ROLES, UserRole, UserStatus
from app.auth.phone import normalize_phone
from app.auth.repository import RefreshTokenRepository
from app.auth.schemas import ProfileUpdate
from app.auth.security import hash_password
from app.cart.models import Cart, CartItem
from app.core.database import conflict_on_integrity_error
from app.core.error_codes import UserErrorCode
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.customers.models import CustomerNote
from app.orders.models import Order
from app.ratings.models import Review, ReviewRequest, ReviewRequestStatus
from app.search_filter.models import SearchHistory
from app.users.models import User, UserIdentity
from app.users.repository import UserRepository
from app.users.schemas import StaffCreate, StaffPasswordReset, StaffQuery, StaffUpdate
from app.users.serializers import staff_read
from app.wishlist.models import Wishlist, WishlistItem


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def create(
        self,
        *,
        role: UserRole,
        tenant_id: UUID,
        email: str,
        phone: str | None = None,
        password: str,
        name: str | None = None,
    ) -> tuple[User, bool]:
        """Create the tenant's user if absent; returns the user and whether it was created."""
        email = email.strip().lower()
        if phone is None and role in STAFF_ROLES:
            raise ValidationError("A phone number is required for staff and admin accounts")
        phone = normalize_phone(phone) if phone else None

        if role in STAFF_ROLES:
            existing = await self.users.get_by_email(
                tenant_id=tenant_id,
                email=email,
                roles=STAFF_ROLES,
            )
            if existing is not None:
                return existing, False

        if phone is not None:
            existing = await self.users.get_by_phone(tenant_id=tenant_id, phone=phone)
            if existing is not None:
                return existing, False

        password_hash = (
            None if role is UserRole.CUSTOMER else await hash_password(password)
        )

        user = await self.users.create(
            tenant_id=tenant_id,
            phone=phone,
            email=email,
            name=name,
            role=role.value,
            password_hash=password_hash,
            is_verified=True,
        )
        await self.session.commit()
        return user, True

    async def update_profile(self, user: User, data: ProfileUpdate) -> User:
        """Change the user's own name and/or email; an email must stay unique per tenant."""
        changes = data.model_dump(exclude_unset=True)

        if "email" in changes and changes["email"] is not None:
            email = str(changes["email"]).strip().lower()
            owner = None
            if user.role in STAFF_ROLES:
                owner = await self.users.get_by_email(
                    tenant_id=user.tenant_id,
                    email=email,
                    roles=STAFF_ROLES,
                )
            if owner is not None and owner.id != user.id:
                raise ConflictError(
                    "That email is already in use", error_code=UserErrorCode.EMAIL_TAKEN
                )
            changes["email"] = email

        for field, value in changes.items():
            setattr(user, field, value)

        async with conflict_on_integrity_error(
            self.session,
            "That email is already in use",
            error_code=UserErrorCode.EMAIL_TAKEN,
        ):
            await self.session.commit()

        return user


class StaffService:
    """Staff and admin logins of the acting admin's store."""

    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.users = UserRepository(session)

    async def get(self, staff_id: UUID) -> User:
        user = await self.users.get_by_id(tenant_id=self.actor.tenant_id, user_id=staff_id)
        if user is None or user.role not in STAFF_ROLES:
            raise NotFoundError("Staff member not found", error_code=UserErrorCode.NOT_FOUND)
        return user

    async def list(self, params: StaffQuery) -> tuple[list[User], int]:
        stmt = select(User).where(
            User.tenant_id == self.actor.tenant_id, User.role.in_(STAFF_ROLES)
        )
        if params.status:
            stmt = stmt.where(User.status == params.status)
        if params.search:
            term = f"%{params.search.strip()}%"
            stmt = stmt.where(
                User.name.ilike(term) | User.email.ilike(term) | User.phone.ilike(term)
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(
            stmt.order_by(User.created_at).offset(params.offset).limit(params.limit)
        )
        return list(rows.all()), int(total or 0)

    async def create(self, data: StaffCreate, request: Request) -> User:
        email = str(data.email).lower()
        if await self.users.get_by_email(
            tenant_id=self.actor.tenant_id,
            email=email,
            roles=STAFF_ROLES,
        ):
            raise ConflictError(
                "That email is already in use", error_code=UserErrorCode.EMAIL_TAKEN
            )
        if await self.users.get_by_phone(tenant_id=self.actor.tenant_id, phone=data.phone):
            raise ConflictError(
                "That phone number is already in use", error_code=UserErrorCode.PHONE_TAKEN
            )

        async with conflict_on_integrity_error(
            self.session, "That email or phone number is already in use"
        ):
            member = await self.users.create(
                tenant_id=self.actor.tenant_id,
                phone=data.phone,
                email=email,
                name=data.name.strip(),
                role=data.role,
                password_hash=await hash_password(data.password),
                is_verified=True,
            )
            member.permissions = data.permissions if data.role == "STAFF" else None
            await record_activity(
                self.session,
                self.actor,
                "staff.created",
                "staff",
                member.id,
                summary=f"Created {data.role.lower()} {email}",
                changes=data.model_dump(exclude={"password"}),
                request=request,
                commit=False,
            )
            await self.session.commit()
        return member

    async def update(self, staff_id: UUID, data: StaffUpdate, request: Request) -> User:
        member = await self.get(staff_id)
        changes = data.model_dump(exclude_unset=True)

        if member.id == self.actor.id and (
            changes.get("status") == UserStatus.INACTIVE.value
            or changes.get("role") == UserRole.STAFF.value
        ):
            raise ValidationError(
                "You cannot deactivate or demote your own account",
                error_code=UserErrorCode.CANNOT_CHANGE_SELF,
            )

        before = staff_read(member).model_dump(include={"name", "role", "permissions", "status"})
        for field, value in changes.items():
            setattr(member, field, value.strip() if field == "name" and value else value)
        if member.role == UserRole.ADMIN.value:
            member.permissions = None

        if changes.get("status") == UserStatus.INACTIVE.value:
            await RefreshTokenRepository(self.session).revoke_all_for_user(member.id)

        await record_activity(
            self.session,
            self.actor,
            "staff.updated",
            "staff",
            member.id,
            summary=f"Updated {member.email or member.phone}",
            changes={"before": before, "after": changes},
            request=request,
            commit=False,
        )
        await self.session.commit()
        return member

    async def reset_password(
        self, staff_id: UUID, data: StaffPasswordReset, request: Request
    ) -> User:
        member = await self.get(staff_id)
        member.password_hash = await hash_password(data.password)
        await RefreshTokenRepository(self.session).revoke_all_for_user(member.id)
        await record_activity(
            self.session,
            self.actor,
            "staff.password_reset",
            "staff",
            member.id,
            summary=f"Reset password for {member.email or member.phone}",
            request=request,
            commit=False,
        )
        await self.session.commit()
        return member


# Erase a customer's personal data on request, per DPDP and GDPR.


class AccountErasureService:
    """Strip the person out of an account without destroying the trade record."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.tokens = RefreshTokenRepository(session)

    async def erase(self, user: User) -> None:
        await self._forget_shopping(user.id)
        await self._detach_reviews(user.id)
        await self._forget_contact(user.id)
        await self._anonymise(user)

        await self.tokens.revoke_all_for_user(user.id)
        await self.session.commit()


    async def _forget_shopping(self, user_id: UUID) -> None:
        """Carts, wishlists, addresses and search history are the person's alone."""
        cart_ids = (
            select(Cart.id)
            .where(Cart.tenant_id == self.tenant_id, Cart.customer_id == user_id)
            .scalar_subquery()
        )
        wishlist_ids = (
            select(Wishlist.id)
            .where(
                Wishlist.tenant_id == self.tenant_id, Wishlist.customer_id == user_id
            )
            .scalar_subquery()
        )

        # Children before parents -- the item tables point back at these rows.
        await self.session.execute(
            delete(CartItem).where(
                CartItem.tenant_id == self.tenant_id, CartItem.cart_id.in_(cart_ids)
            )
        )
        await self.session.execute(
            delete(Cart).where(
                Cart.tenant_id == self.tenant_id, Cart.customer_id == user_id
            )
        )

        await self.session.execute(
            delete(WishlistItem).where(
                WishlistItem.tenant_id == self.tenant_id,
                WishlistItem.wishlist_id.in_(wishlist_ids),
            )
        )
        await self.session.execute(
            delete(Wishlist).where(
                Wishlist.tenant_id == self.tenant_id, Wishlist.customer_id == user_id
            )
        )

        await self.session.execute(
            delete(Address).where(
                Address.tenant_id == self.tenant_id, Address.customer_id == user_id
            )
        )
        await self.session.execute(
            delete(SearchHistory).where(
                SearchHistory.tenant_id == self.tenant_id,
                SearchHistory.user_id == user_id,
            )
        )

    async def _detach_reviews(self, user_id: UUID) -> None:
        """Reviews stay up for other shoppers; they just stop naming an author."""
        await self.session.execute(
            update(Review)
            .where(Review.tenant_id == self.tenant_id, Review.user_id == user_id)
            .values(user_id=None)
        )

    async def _forget_contact(self, user_id: UUID) -> None:
        """Orders keep the delivery record, but not the contact email or review prompts."""
        await self.session.execute(
            delete(CustomerNote).where(
                CustomerNote.tenant_id == self.tenant_id, CustomerNote.customer_id == user_id
            )
        )

        await self.session.execute(
            update(Order)
            .where(Order.tenant_id == self.tenant_id, Order.customer_id == user_id)
            .values(contact_email=None)
        )
        await self.session.execute(
            update(ReviewRequest)
            .where(
                ReviewRequest.tenant_id == self.tenant_id,
                ReviewRequest.customer_id == user_id,
                ReviewRequest.status.in_(
                    [ReviewRequestStatus.PENDING.value, ReviewRequestStatus.SENT.value]
                ),
            )
            .values(status=ReviewRequestStatus.CANCELLED.value)
        )

    async def _anonymise(self, user: User) -> None:
        """Orders keep their delivery details -- tax law requires the record."""
        await self.session.execute(
            delete(UserIdentity).where(
                UserIdentity.tenant_id == self.tenant_id,
                UserIdentity.user_id == user.id,
            )
        )
        user.phone = None
        user.email = None
        user.name = None
        user.tags = None
        user.status = UserStatus.DELETED.value
        user.is_verified = False
