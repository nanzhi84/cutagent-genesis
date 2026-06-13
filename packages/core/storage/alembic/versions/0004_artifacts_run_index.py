from __future__ import annotations

from alembic import op

revision = "0004_artifacts_run_index"
down_revision = "0003_selection_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_artifacts_run", "artifacts", ["run_id"])
    op.create_index("idx_artifacts_run_kind", "artifacts", ["run_id", "kind"])


def downgrade() -> None:
    op.drop_index("idx_artifacts_run_kind", table_name="artifacts")
    op.drop_index("idx_artifacts_run", table_name="artifacts")
