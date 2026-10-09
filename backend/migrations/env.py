from alembic import context
from sqlmodel import SQLModel

from app import models  # noqa: F401
from app.config import Settings
from app.db import make_engine

settings = context.config.attributes.get("settings") or Settings()


def migrate(connection):
    context.configure(
        connection=connection, target_metadata=SQLModel.metadata, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    migrate(connection)
else:
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
