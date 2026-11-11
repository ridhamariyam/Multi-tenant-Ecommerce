from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.constants import UserRole, UserStatus
from app.auth.security import create_access_token, hash_password
from app.core import cache, rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.models.registry import Base
from app.pricing.defaults import ensure_default_rules
from app.tenants.models import Tenant, TenantDomain
from app.users.models import User
from tests.helpers import shared_data
from tests.tax import TaxSetup, sign_off_tax

settings = get_settings()

_SHARED = shared_data()

ZEEN_DOMAIN = _SHARED["domains"]["zeen"]
ACME_DOMAIN = _SHARED["domains"]["acme"]
UNREGISTERED_DOMAIN = _SHARED["domains"]["unregistered"]

ADMIN_PASSWORD = _SHARED["passwords"]["admin"]


def _readable(name: str) -> str:
    """test_a_code_expires[5] -> "a code expires[5]"."""
    base, bracket, params = name.partition("[")
    words = base.removeprefix("test_").replace("_", " ")
    return f"{words}{bracket}{params}"


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        module, separator, name = item._nodeid.rpartition("::")
        if separator:
            item._nodeid = f"{module}{separator}{_readable(name)}"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise pytest.UsageError(f"{name} must be set explicitly for backend tests")
    return value


def _required_int(name: str) -> int:
    try:
        return int(_required_env(name))
    except ValueError as exc:
        raise pytest.UsageError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class TestTargets:
    database_url: str
    database_name: str
    server_addr: str
    server_port: int
    redis_url: str
    redis_marker: str


@pytest.fixture(scope="session", autouse=True)
def _test_targets() -> TestTargets:
    database_url = _required_env("TEST_DATABASE_URL")
    db = make_url(database_url)
    app_db = make_url(settings.database_url)
    allowed_host = _required_env("TEST_DATABASE_ALLOWED_HOST")
    allowed_port = _required_int("TEST_DATABASE_ALLOWED_PORT")
    allowed_name = _required_env("TEST_DATABASE_ALLOWED_NAME")
    server_addr = _required_env("TEST_DATABASE_ALLOWED_SERVER_ADDR")
    server_port = _required_int("TEST_DATABASE_ALLOWED_SERVER_PORT")

    if (
        db.drivername != "postgresql+asyncpg"
        or not db.host
        or not db.database
        or not db.port
        or db.query
    ):
        raise pytest.UsageError("TEST_DATABASE_URL must name an explicit PostgreSQL host, port and database")
    if (db.host, db.port, db.database) != (allowed_host, allowed_port, allowed_name):
        raise pytest.UsageError("TEST_DATABASE_URL is not on the explicit database allowlist")
    if db.database == app_db.database:
        raise pytest.UsageError("Test database must differ from the application database")
    if not (1 <= allowed_port <= 65535 and 1 <= server_port <= 65535):
        raise pytest.UsageError("Invalid allowed PostgreSQL port")

    redis_url = _required_env("TEST_REDIS_URL")
    target = urlsplit(redis_url)
    app_redis = urlsplit(settings.redis_url)
    allowed_redis = (
        _required_env("TEST_REDIS_ALLOWED_HOST"),
        _required_int("TEST_REDIS_ALLOWED_PORT"),
        _required_int("TEST_REDIS_ALLOWED_DB"),
    )
    try:
        redis_db = int(target.path.lstrip("/"))
    except ValueError as exc:
        raise pytest.UsageError("TEST_REDIS_URL must specify a numeric database") from exc
    if (
        target.scheme not in {"redis", "rediss"}
        or not target.hostname
        or target.port is None
        or target.query
        or target.fragment
        or not target.path.startswith("/")
        or target.path.count("/") != 1
        or (target.hostname, target.port, redis_db) != allowed_redis
    ):
        raise pytest.UsageError("TEST_REDIS_URL is not on the explicit Redis allowlist")
    if (target.hostname, target.port) == (app_redis.hostname, app_redis.port or 6379):
        raise pytest.UsageError("Tests require a dedicated Redis server, separate from the application")
    if not 0 <= redis_db <= 15:
        raise pytest.UsageError("Invalid test Redis database number")

    return TestTargets(
        database_url=database_url,
        database_name=allowed_name,
        server_addr=server_addr,
        server_port=server_port,
        redis_url=redis_url,
        redis_marker=_required_env("TEST_REDIS_INSTANCE_ID"),
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _isolated_redis(_test_targets: TestTargets) -> AsyncGenerator[None, None]:
    if cache._client is not None:
        raise pytest.UsageError("An application Redis client was initialized before test isolation")
    client = redis.Redis.from_url(_test_targets.redis_url, decode_responses=True)
    try:
        marker = await client.get("cliq:test:instance-id")
        if marker != _test_targets.redis_marker:
            raise pytest.UsageError("Dedicated test Redis instance marker did not match")
        original_cache_get_redis = cache.get_redis
        original_rate_get_redis = rate_limit.get_redis
        original_prefix = rate_limit.KEY_PREFIX
        cache.get_redis = lambda: client
        rate_limit.get_redis = lambda: client
        rate_limit.KEY_PREFIX = f"ratelimit:test:{uuid.uuid4().hex}"
        try:
            yield
        finally:
            rate_limit.KEY_PREFIX = original_prefix
            rate_limit.get_redis = original_rate_get_redis
            cache.get_redis = original_cache_get_redis
    finally:
        await client.aclose()


@pytest_asyncio.fixture(loop_scope="session")
async def engine(_test_targets: TestTargets, _isolated_redis):
    # Each test gets a newly named schema, dropped again when the test ends.
    # Only that schema is dropped: existing databases and schemas are never
    # dropped, truncated or recreated by the fixture.
    schema = f"cliq_test_{uuid.uuid4().hex}"

    async def on_allowed_target(connection, refusal: str) -> None:
        actual = (await connection.exec_driver_sql(
            "SELECT current_database(), host(inet_server_addr()), inet_server_port()"
        )).one()
        if actual != (
            _test_targets.database_name,
            _test_targets.server_addr,
            _test_targets.server_port,
        ):
            raise pytest.UsageError(refusal)

    admin_engine = create_async_engine(_test_targets.database_url)
    try:
        async with admin_engine.begin() as connection:
            await on_allowed_target(
                connection, "PostgreSQL target does not match the verified allowlist"
            )
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        engine = create_async_engine(
            _test_targets.database_url,
            connect_args={"server_settings": {"search_path": schema}},
        )
        try:
            async with engine.begin() as connection:
                await on_allowed_target(
                    connection, "PostgreSQL target changed before schema setup"
                )
            yield engine
        finally:
            await engine.dispose()
            async with admin_engine.begin() as connection:
                await on_allowed_target(
                    connection, "PostgreSQL target changed before schema teardown"
                )
                await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
    finally:
        await admin_engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # The migration seeds the system GST rules; create_all does not.
        await ensure_default_rules(session)
        yield session


async def _client_for(session: AsyncSession, domain: str) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=f"http://{domain}") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async for c in _client_for(session, ZEEN_DOMAIN):
        yield c


@pytest_asyncio.fixture(loop_scope="session")
async def other_client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async for c in _client_for(session, ACME_DOMAIN):
        yield c


@dataclass
class FakeMsg91:
    """Stands in for MSG91's widget verification.

    The real exchange is covered against a mocked transport in
    tests/auth/test_widget.py; here it is stubbed so that every other suite
    can sign a customer in without reaching the network.
    """

    verified: dict[str, str]

    def token_for(self, phone: str) -> str:
        token = f"widget-token-{len(self.verified) + 1}"
        self.verified[token] = phone
        return token


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def msg91(monkeypatch) -> FakeMsg91:
    fake = FakeMsg91(verified={})

    async def verify(access_token: str) -> str:
        phone = fake.verified.get(access_token)
        if phone is None:
            raise AuthenticationError("Could not verify that number")
        return phone

    monkeypatch.setattr("app.auth.service.verify_access_token", verify)
    return fake


@pytest_asyncio.fixture(loop_scope="session")
async def tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Zeen", slug="zeen", is_active=True)
    session.add(tenant)
    await session.flush()
    session.add(TenantDomain(tenant_id=tenant.id, domain=ZEEN_DOMAIN))
    await session.commit()
    return tenant


@pytest_asyncio.fixture(loop_scope="session")
async def other_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    session.add(tenant)
    await session.flush()
    session.add(TenantDomain(tenant_id=tenant.id, domain=ACME_DOMAIN))
    await session.commit()
    return tenant


@pytest_asyncio.fixture(loop_scope="session")
async def tax_ready(session: AsyncSession, tenant: Tenant) -> TaxSetup:
    """The tenant's GST and HSN rates signed off, so checkout can price a basket.

    Suites that check out request it autouse from their conftest; see tests/tax.py.
    """
    return await sign_off_tax(session, tenant)


@pytest_asyncio.fixture(loop_scope="session")
async def make_user(session: AsyncSession):
    counter = {"n": 0}

    async def _make(
        *,
        tenant: Tenant,
        phone: str | None = None,
        email: str | None = None,
        name: str | None = None,
        role: str = UserRole.CUSTOMER.value,
        password: str = ADMIN_PASSWORD,
        status: str = UserStatus.ACTIVE.value,
    ) -> User:
        counter["n"] += 1
        is_staff = role != UserRole.CUSTOMER.value

        if phone is None:
            phone = f"+91900000{counter['n']:04d}"
        user = User(
            tenant_id=tenant.id,
            phone=phone,
            email=email,
            name=name,
            role=role,
            status=status,
            password_hash=await hash_password(password) if is_staff else None,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        return user

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def user(make_user, tenant: Tenant) -> User:
    return await make_user(tenant=tenant, phone="+919876543210")


def token_for(user: User) -> str:
    return create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)


def headers_for(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}"}


async def widget_login(client: AsyncClient, access_token: str):
    return await client.post(
        "/api/v1/auth/widget/login", json={"access_token": access_token}
    )


async def sign_in_customer(client: AsyncClient, msg91: FakeMsg91, phone: str) -> dict:
    response = await widget_login(client, msg91.token_for(phone))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def admin_login(
    client: AsyncClient,
    identifier: str,
    password: str = ADMIN_PASSWORD,
):
    return await client.post(
        "/api/v1/admin/auth/login",
        json={"identifier": identifier, "password": password},
    )


async def sign_in_admin(
    client: AsyncClient,
    identifier: str,
    password: str = ADMIN_PASSWORD,
) -> dict:
    response = await admin_login(client, identifier, password)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def sign_in_staff(
    client: AsyncClient,
    identifier: str,
    password: str = ADMIN_PASSWORD,
) -> dict:
    response = await client.post(
        "/api/v1/staff/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest_asyncio.fixture(loop_scope="session")
async def admin_headers(tenant, make_user) -> dict[str, str]:
    admin = await make_user(
        tenant=tenant, email="admin@zeen.com", role=UserRole.ADMIN.value
    )
    return headers_for(admin)


@pytest_asyncio.fixture(loop_scope="session")
async def staff_headers(tenant, make_user) -> dict[str, str]:
    staff = await make_user(
        tenant=tenant, email="staff@zeen.com", role=UserRole.STAFF.value
    )
    return headers_for(staff)


@pytest_asyncio.fixture(loop_scope="session")
async def customer_headers(tenant, make_user) -> dict[str, str]:
    customer = await make_user(tenant=tenant, phone="+919000111222")
    return headers_for(customer)


@pytest_asyncio.fixture(loop_scope="session")
async def other_admin_headers(other_tenant, make_user) -> dict[str, str]:
    admin = await make_user(
        tenant=other_tenant, email="admin@acme.com", role=UserRole.ADMIN.value
    )
    return headers_for(admin)
