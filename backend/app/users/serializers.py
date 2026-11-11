from __future__ import annotations

from app.auth.constants import UserRole
from app.auth.permissions import effective_permissions
from app.users.models import User
from app.users.schemas import StaffRead


def staff_read(user: User) -> StaffRead:
    return StaffRead(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        status=user.status,
        permissions=None if user.role == UserRole.ADMIN.value else user.permissions,
        effective_permissions=sorted(effective_permissions(user.role, user.permissions)),
        created_at=user.created_at,
    )
