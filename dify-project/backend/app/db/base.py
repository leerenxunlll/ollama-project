"""Declarative base for future SQLAlchemy models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future database models; no tables are defined in Phase 0."""
