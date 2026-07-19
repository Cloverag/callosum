"""Alembic environment for Meridian's product-domain schema.

We reuse Callosum's own database settings so there is a single source of truth for
the connection string. Migrations are hand-written (no autogenerate) to keep them
explicit and reviewable, matching the repo's raw-SQL schema style.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from callosum.config import settings

config = context.config

# Callosum stores a plain libpq URL (postgresql://...). SQLAlchemy needs to know
# which driver to use, so we pin psycopg (v3), which the project already depends on.
_url = settings().postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", _url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Hand-written migrations, so no model metadata to autogenerate against.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
