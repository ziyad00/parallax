"""Test fixture — minimal SQLAlchemy model file."""

from __future__ import annotations


class Base:
    """Stand-in for SQLAlchemy declarative base."""


class User(Base):
    pass


class Order(Base):
    pass


class LineItem(Base):
    pass
