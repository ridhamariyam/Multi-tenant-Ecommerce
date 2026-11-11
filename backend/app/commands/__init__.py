"""Operational commands (`python -m app.commands.<name>`).

Every model is imported up front: a command that touches one table must still
resolve foreign keys to tables it never imports itself (e.g. tenants →
merchant_accounts). Without this, running a command outside the API process
fails with NoReferencedTableError.
"""

import app.models.registry  # noqa: F401
