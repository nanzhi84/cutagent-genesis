from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015_publish_accounts"
down_revision = "0014_drop_legacy_case_agent"
branch_labels = None
depends_on = None


# Publishing center PR2: client / publish-account / case→account binding foundation.
#   - clients               (客户/品牌 we publish on behalf of)
#   - publish_accounts       (a client's per-platform account; encrypted browser
#                             session lives in the SecretStore, only the ref is here)
#   - case_publish_targets   (a Case publishes to a selected set of its client's accounts)
#
# Idempotent: 0001 bootstraps via Base.metadata.create_all(), so fresh DBs already
# have these tables. Inspect first so this migration is a no-op there but still
# applies on pre-existing databases.

_TIMESTAMP_COLUMNS = (
    sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="v1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "clients" not in existing_tables:
        op.create_table(
            "clients",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("remark", sa.String(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            *_TIMESTAMP_COLUMNS,
        )

    if "publish_accounts" not in existing_tables:
        op.create_table(
            "publish_accounts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "client_id", sa.String(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("platform", sa.String(), nullable=False),
            sa.Column("account_name", sa.String(), nullable=False),
            sa.Column("platform_uid", sa.String(), nullable=True),
            sa.Column("session_secret_ref", sa.String(), nullable=True),
            sa.Column("session_status", sa.String(), nullable=False, server_default="never_logged_in"),
            sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            *_TIMESTAMP_COLUMNS,
            sa.UniqueConstraint(
                "client_id", "platform", "account_name", name="uq_publish_accounts_client_platform_name"
            ),
        )

    if "case_publish_targets" not in existing_tables:
        op.create_table(
            "case_publish_targets",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "case_id", sa.String(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column(
                "account_id",
                sa.String(),
                sa.ForeignKey("publish_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            *_TIMESTAMP_COLUMNS,
            sa.UniqueConstraint("case_id", "account_id", name="uq_case_publish_targets_case_account"),
        )


def downgrade() -> None:
    op.drop_table("case_publish_targets")
    op.drop_table("publish_accounts")
    op.drop_table("clients")
