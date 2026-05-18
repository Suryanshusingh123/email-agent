from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Import our app's engine and models so Alembic can:
# 1. Use our database URL (not the one in alembic.ini)
# 2. Detect model changes for autogenerate
from app.database import engine, Base
import app.models.db_models  # noqa: F401 — must be imported so Base sees the tables

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is what enables `alembic revision --autogenerate`
# It compares Base.metadata (your models) against the live database schema
# and generates the SQL diff automatically
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations using just the URL — no live DB connection needed."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    # Use our existing engine instead of creating a new one from alembic.ini
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
