"""ORM models for the s7117_rel database.

- inspections: the primary domain entity (DOMAIN_ID 5 - restaurant
  inspections): auto-increment id, facility_name (primary field),
  site_address (secondary field). HW5 adds inspection_code (unique,
  INS-######), score (0-100, default 100), inspector_id (FK) and timestamps.
- inspectors: the related entity (HW5) - one inspector performs many
  inspections; deleting an inspector that still has inspections is rejected
  (FK ON DELETE RESTRICT, no cascade).
- inspection_violations: the related test data for the N+1 experiment
  (200 rows, each belonging to one inspection).
- users: login accounts for JWT auth (HW7 adds username + role; only the
  PBKDF2 password hash is stored). The HW4 `sessions` table still exists in
  MySQL but is no longer mapped or used (kept as history at the hw4 tag).

Tables are created by code/hw04/schema.sql, code/hw05/migration.sql and
code/hw07/migration.sql (the committed migrations), not by Base.metadata.create_all(), so the index
experiment starts from a known state.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Inspector(Base):
    __tablename__ = "inspectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    district: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # passive_deletes: let MySQL's ON DELETE RESTRICT reject the delete instead
    # of the ORM trying to null out inspector_id on the children.
    inspections: Mapped[list["Inspection"]] = relationship(
        back_populates="inspector", passive_deletes="all", lazy="select"
    )


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inspection_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    facility_name: Mapped[str] = mapped_column(String(255), nullable=False)
    site_address: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    inspector_id: Mapped[int] = mapped_column(
        ForeignKey("inspectors.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    inspector: Mapped[Inspector] = relationship(back_populates="inspections")

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
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # reader | writer | moderator (CHECK constraint in code/hw07/migration.sql)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="reader")
