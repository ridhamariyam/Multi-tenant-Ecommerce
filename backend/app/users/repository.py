from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import AuthProvider, UserRole, UserStatus
from app.users.models import User, UserIdentity


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        phone: str | None = None,
        role: str = UserRole.CUSTOMER.value,
        email: str | None = None,
        name: str | None = None,
        password_hash: str | None = None,
        is_verified: bool = False,
    ) -> User:
        user = User(
            tenant_id=tenant_id,
            phone=phone,
            role=role,
            email=email,
            name=name,
            password_hash=password_hash,
            status=UserStatus.ACTIVE.value,
            is_verified=is_verified,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, *, tenant_id: UUID, user_id: UUID) -> User | None:
        return await self.session.scalar(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )

    async def get_by_phone(self, *, tenant_id: UUID, phone: str) -> User | None:
        return await self.session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.phone == phone)
        )

    async def get_by_email(
        self,
        *,
        tenant_id: UUID,
        email: str,
        roles: frozenset[str] | None = None,
    ) -> User | None:
        stmt = select(User).where(User.tenant_id == tenant_id, User.email == email)
        if roles is not None:
            stmt = stmt.where(User.role.in_(roles))
        stmt = stmt.order_by(User.created_at).limit(1)
        return await self.session.scalar(stmt)

    async def email_exists(
        self, *, tenant_id: UUID, email: str, roles: frozenset[str] | None = None
    ) -> bool:
        stmt = select(User.id).where(User.tenant_id == tenant_id, User.email == email)
        if roles is not None:
            stmt = stmt.where(User.role.in_(roles))
        return await self.session.scalar(stmt.limit(1)) is not None

    async def get_by_identity(
        self,
        *,
        tenant_id: UUID,
        provider: str,
        subject: str,
    ) -> User | None:
        return await self.session.scalar(
            select(User)
            .join(
                UserIdentity,
                (UserIdentity.user_id == User.id)
                & (UserIdentity.tenant_id == User.tenant_id),
            )
            .where(
                UserIdentity.tenant_id == tenant_id,
                UserIdentity.provider == provider,
                UserIdentity.subject == subject,
                User.tenant_id == tenant_id,
            )
        )

    async def get_by_email_identity(
        self,
        *,
        tenant_id: UUID,
        email: str,
    ) -> User | None:
        return await self.get_by_identity(
            tenant_id=tenant_id,
            provider=AuthProvider.EMAIL.value,
            subject=email.strip().lower(),
        )

    async def add_identity(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        provider: str,
        subject: str,
    ) -> UserIdentity:
        identity = UserIdentity(
            tenant_id=tenant_id,
            user_id=user_id,
            provider=provider,
            subject=subject,
        )
        self.session.add(identity)
        await self.session.flush()
        return identity
