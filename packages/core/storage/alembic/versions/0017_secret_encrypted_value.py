from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_secret_encrypted_value"
down_revision = "0016_finished_video_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("secrets")}
    if "encrypted_value" not in columns:
        op.add_column("secrets", sa.Column("encrypted_value", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("secrets")}
    if "encrypted_value" in columns:
        op.drop_column("secrets", "encrypted_value")
