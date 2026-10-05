"""Create database tables from the registered SQLAlchemy models."""

from sqlalchemy.engine import Engine

from app.db.base import Base
from app.models import (  # noqa: F401
    Character,
    Clue,
    GameCharacter,
    GameSession,
    Message,
    Script,
)


def create_tables(engine: Engine) -> None:
    """Create missing tables; schema changes are not applied to existing tables."""
    Base.metadata.create_all(bind=engine)
