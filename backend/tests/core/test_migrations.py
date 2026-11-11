from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import app.models.registry as registry
from app.models.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "tenants",
    "tenant_domains",
    "users",
    "otp_requests",
    "refresh_tokens",
    "categories",
    "products",
    "product_variants",
}


def _import_in_fresh_interpreter(module: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )


def test_the_app_imports_the_way_uvicorn_imports_it():
    result = _import_in_fresh_interpreter("app.main")

    assert result.returncode == 0, result.stderr


def test_the_registry_imports_standalone():
    result = _import_in_fresh_interpreter("app.models.registry")

    assert result.returncode == 0, result.stderr


def test_every_model_is_registered_on_the_metadata():
    registered = set(Base.metadata.tables)

    assert registered >= EXPECTED_TABLES, (
        f"missing from Base.metadata: {EXPECTED_TABLES - registered}. "
        "Add the model to app/models/registry.py."
    )


def test_registry_exports_every_model():
    expected = (
        "Base",
        "Tenant",
        "TenantDomain",
        "User",
        "OtpRequest",
        "RefreshToken",
        "Category",
        "Product",
        "ProductVariant",
    )
    for name in expected:
        assert name in registry.__all__
        assert hasattr(registry, name)


def test_constraints_follow_the_naming_convention():
    users = Base.metadata.tables["users"]

    assert users.primary_key.name == "pk_users"
    assert {fk.constraint.name for fk in users.foreign_keys} == {"fk_users_tenant_id_tenants"}
