"""added table address

Revision ID: 39e4c6a79e2f
Revises: 8941b66b24e2
Create Date: 2022-01-26 09:09:37.784056

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "39e4c6a79e2f"
down_revision = "8941b66b24e2"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "address",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("date_created", sa.Date(), nullable=True),
        sa.Column("date_updated", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "spatial_ref_sys",
        sa.Column("srid", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column(
            "auth_name", sa.VARCHAR(length=256), autoincrement=False, nullable=True
        ),
        sa.Column("auth_srid", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column(
            "srtext", sa.VARCHAR(length=2048), autoincrement=False, nullable=True
        ),
        sa.Column(
            "proj4text", sa.VARCHAR(length=2048), autoincrement=False, nullable=True
        ),
        sa.CheckConstraint(
            "(srid > 0) AND (srid <= 998999)", name="spatial_ref_sys_srid_check"
        ),
        sa.PrimaryKeyConstraint("srid", name="spatial_ref_sys_pkey"),
    )
    op.drop_table("address")
    # ### end Alembic commands ###
