from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_media_thumbnail_duration"
down_revision = "0005_case_profile_and_brief"
branch_labels = None
depends_on = None


# (column_name, sqlalchemy type, nullable) for media_assets. All nullable with no
# server default: the card thumbnail/dimension fields are optional metadata that
# back-fill lazily, so the add is safe on populated tables.
_MEDIA_ASSET_COLUMNS = (
    ("thumbnail_uri", sa.Text(), True),
    ("duration_sec", sa.Float(), True),
    ("width", sa.Integer(), True),
    ("height", sa.Integer(), True),
)


def _add_missing_columns(bind, table: str, columns) -> None:
    existing = {col["name"] for col in sa.inspect(bind).get_columns(table)}
    for name, type_, nullable in columns:
        if name in existing:
            continue
        op.add_column(table, sa.Column(name, type_, nullable=nullable))


def _drop_columns(bind, table: str, columns) -> None:
    existing = {col["name"] for col in sa.inspect(bind).get_columns(table)}
    for name, *_ in columns:
        if name in existing:
            op.drop_column(table, name)


def upgrade() -> None:
    # 0001_initial_schema bootstraps the schema via Base.metadata.create_all(), which
    # already includes these columns on fresh databases (declared on MediaAssetRow).
    # Inspect existing columns first so this migration is a no-op on create_all DBs,
    # while still applying on databases provisioned before the columns were added.
    bind = op.get_bind()
    _add_missing_columns(bind, "media_assets", _MEDIA_ASSET_COLUMNS)


def downgrade() -> None:
    bind = op.get_bind()
    _drop_columns(bind, "media_assets", _MEDIA_ASSET_COLUMNS)
