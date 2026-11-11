"""Merchant sign-up, sign-in and platform session rotation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import (
    hash_password,
    hash_refresh_token,
    spend_dummy_verification,
    verify_password,
)
from app.core.config import get_settings
from app.core.error_codes import AuthErrorCode, MerchantErrorCode
from app.core.exceptions import AuthenticationError, ConflictError, PermissionDeniedError
from app.merchants.models import MerchantAccount, MerchantRefreshToken
from app.merchants.schemas import (
    MerchantAccountRead,
    MerchantLogin,
    MerchantRegister,
    MerchantSession,
)
from app.merchants.security import (
    create_merchant_token,
    decode_merchant_token,
    merchant_access_lifetime_seconds,
)

INVALID_CREDENTIALS = "Invalid email or password"
INVALID_TOKEN = "Invalid authentication credentials"


class MerchantAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> MerchantAccount | None:
        return await self.session.scalar(
            select(MerchantAccount).where(MerchantAccount.email == email.strip().lower())
        )

    async def register(self, data: MerchantRegister) -> MerchantSession:
        if await self.get_by_email(data.email) is not None:
            raise ConflictError(
                "An account with this email already exists",
                error_code=MerchantErrorCode.EMAIL_TAKEN,
            )
        account = MerchantAccount(
            email=data.email,
            name=data.name.strip(),
            phone=data.phone,
            password_hash=await hash_password(data.password),
        )
        self.session.add(account)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "An account with this email already exists",
                error_code=MerchantErrorCode.EMAIL_TAKEN,
            ) from exc
        await self.session.refresh(account)
        session = await self._issue(account)
        await self.session.commit()
        return session

    async def login(self, data: MerchantLogin) -> MerchantSession:
        account = await self.get_by_email(data.email)
        if account is None:
            # Same work as a real check, so timing does not reveal which emails exist.
            await spend_dummy_verification()
            raise AuthenticationError(
                INVALID_CREDENTIALS, error_code=AuthErrorCode.INVALID_CREDENTIALS
            )
        if not await verify_password(data.password, account.password_hash):
            raise AuthenticationError(
                INVALID_CREDENTIALS, error_code=AuthErrorCode.INVALID_CREDENTIALS
            )
        if not account.is_active:
            raise PermissionDeniedError(
                "This account is suspended", error_code=MerchantErrorCode.ACCOUNT_SUSPENDED
            )
        account.last_login_at = datetime.now(timezone.utc)
        session = await self._issue(account)
        await self.session.commit()
        return session

    async def refresh(self, refresh_token: str) -> MerchantSession:
        payload = decode_merchant_token(refresh_token, expected_type="merchant_refresh")
        stored = await self.session.scalar(
            select(MerchantRefreshToken)
            .where(MerchantRefreshToken.token_hash == hash_refresh_token(refresh_token))
            .with_for_update()
        )
        if stored is None or stored.account_id != payload.account_id:
            raise AuthenticationError(INVALID_TOKEN, error_code=AuthErrorCode.INVALID_TOKEN)

        now = datetime.now(timezone.utc)
        grace = timedelta(seconds=get_settings().refresh_reuse_grace_seconds)
        rotated_moments_ago = stored.replaced_at is not None and now - stored.replaced_at <= grace
        if stored.revoked_at is not None and not rotated_moments_ago:
            # A rotated token presented again: treat the family as stolen.
            await self._revoke_all(stored.account_id, now)
            await self.session.commit()
            raise AuthenticationError(INVALID_TOKEN, error_code=AuthErrorCode.INVALID_TOKEN)
        if stored.expires_at <= now:
            raise AuthenticationError(INVALID_TOKEN, error_code=AuthErrorCode.INVALID_TOKEN)

        account = await self.session.get(MerchantAccount, stored.account_id)
        if account is None or not account.is_active:
            raise AuthenticationError(INVALID_TOKEN, error_code=AuthErrorCode.INVALID_TOKEN)

        if stored.revoked_at is None:
            stored.revoked_at = now
            stored.replaced_at = now
        session = await self._issue(account)
        await self.session.commit()
        return session

    async def logout(self, refresh_token: str) -> None:
        stored = await self.session.scalar(
            select(MerchantRefreshToken).where(
                MerchantRefreshToken.token_hash == hash_refresh_token(refresh_token)
            )
        )
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(timezone.utc)
            await self.session.commit()

    async def _revoke_all(self, account_id, now: datetime) -> None:
        await self.session.execute(
            update(MerchantRefreshToken)
            .where(
                MerchantRefreshToken.account_id == account_id,
                MerchantRefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def _issue(self, account: MerchantAccount) -> MerchantSession:
        refresh = create_merchant_token(account.id, "merchant_refresh")
        self.session.add(
            MerchantRefreshToken(
                account_id=account.id,
                token_hash=hash_refresh_token(refresh),
                expires_at=datetime.now(timezone.utc)
                + timedelta(days=get_settings().merchant_refresh_token_expire_days),
            )
        )
        await self.session.flush()
        return MerchantSession(
            access_token=create_merchant_token(account.id, "merchant_access"),
            refresh_token=refresh,
            expires_in=merchant_access_lifetime_seconds(),
            account=MerchantAccountRead.model_validate(account),
        )
