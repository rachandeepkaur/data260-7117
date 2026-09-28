"""ORM models for the s7117_rel database.

- inspections: the primary domain entity (DOMAIN_ID 5 - restaurant
  inspections): auto-increment id, facility_name (primary field),
  site_address (secondary field).
- inspection_violations: the related test data for the N+1 experiment
  (200 rows, each belonging to one inspection).
- users / sessions: authentication and server-side session storage.

Tables are created by code/hw04/schema.sql (the committed migration), not by
Base.metadata.create_all(), so the index experiment starts from a known state.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    facility_name: Mapped[str] = mapped_column(String(255), nullable=False)
    site_address: Mapped[str] = mapped_column(String(255), nullable=False)

    violations: Mapped[list["Violation"]] = relationship(
        back_populates="inspection",
        order_by="Violation.id",
        cascade="all, delete-orphan",
        lazy="select",
    )


class Violation(Base):
    __tablename__ = "inspection_violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ForeignKey here only tells the ORM how the tables relate; schema.sql
    # deliberately has no FK constraint/index on this column (InnoDB would
    # auto-create an index for an FK), so the index step starts from a scan.
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), nullable=False)
    violation_code: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    points_deducted: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)

    inspection: Mapped[Inspection] = relationship(back_populates="violations")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class UserSession(Base):
    __tablename__ = "sessions"

    # The opaque session token itself; the browser cookie holds only this value.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped[User] = relationship()
