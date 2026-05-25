"""Alembic environment, wired to the application's own config and metadata.

Two things matter here and are easy to get wrong:

* The URL comes from `backend.config.get_settings()`, not from `alembic.ini`.
  That keeps one source of truth: the deployed pod, the test run and a local
  shell all migrate whatever `DATABASE_URL` points at, and no database
  credential is ever written into a file that gets committed.
* `render_as_batch` is on for SQLite, which cannot `ALTER` most things in
  place. Alembic emulates it by rebuilding the table. Postgres ignores the
  setting, so the same migration script runs on both.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.config import get_settings
from backend.database import Base

# Importing the models module is what populates Base.metadata. Without it
# autogenerate sees an empty schema and helpfully offers to drop every table.
from backend import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting. Useful for reviewing a migration."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(url),
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_is_sqlite(url),
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
