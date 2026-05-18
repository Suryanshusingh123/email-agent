"""
database.py — SQLAlchemy engine, session factory, and base class.

THREE THINGS THIS FILE PROVIDES:
  1. engine      — the connection to your database (one per app)
  2. SessionLocal — a factory that creates database sessions
  3. Base        — the class all ORM models inherit from

WHY SEPARATE THIS FROM MODELS?
  If models imported the engine and the engine imported models, you'd have
  circular imports. This file has no imports from the rest of your app —
  everything else imports FROM here.

SESSION VS CONNECTION:
  A connection is a raw TCP connection to the database.
  A session is a higher-level object that tracks changes (adds, updates,
  deletes) and commits them together as a transaction.
  Always use sessions in application code — never raw connections.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

# --- Engine ---
# The engine manages the connection pool to your database.
# connect_args={"check_same_thread": False} is SQLite-specific —
# SQLite by default only allows one thread. FastAPI uses multiple threads,
# so we disable that restriction. PostgreSQL doesn't need this.
connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,  # Set True to print every SQL query — useful for debugging
)

# --- Session factory ---
# SessionLocal() creates a new database session.
# autocommit=False → you must explicitly call session.commit()
# autoflush=False  → SQLAlchemy won't auto-sync to DB mid-transaction
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# --- Declarative base ---
# All ORM model classes inherit from Base.
# This gives SQLAlchemy the metadata it needs to create tables
# and map Python classes to database rows.
class Base(DeclarativeBase):
    pass


# --- FastAPI dependency ---
def get_db():
    """
    Yield a database session for use in FastAPI endpoints.

    WHY A GENERATOR (yield)?
      FastAPI's dependency injection system calls this function, runs the
      endpoint, then resumes after the yield to run cleanup.
      This guarantees the session is always closed — even if the endpoint
      raises an exception. No connection leaks.

    USAGE IN ENDPOINTS:
      from fastapi import Depends
      from app.database import get_db
      from sqlalchemy.orm import Session

      @router.get("/something")
      def my_endpoint(db: Session = Depends(get_db)):
          results = db.query(EmailRecord).all()
          return results
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
