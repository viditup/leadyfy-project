"""
Database engine and session management (SQLAlchemy).
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    # Needed for SQLite when accessed from multiple threads (FastAPI's
    # default threadpool for sync endpoints).
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

# Part 5 DB-integrity fix: SQLite does NOT enforce FOREIGN KEY constraints
# by default -- every column declared `ForeignKey(...)` in app/models/*.py
# was, until now, purely documentation as far as the database itself was
# concerned. Several services already had comments acknowledging this and
# compensating with manual existence checks (e.g. order_service.create_order,
# finance_service.create_creator_payout); this turns on real enforcement as
# a second, DB-level line of defense, catching any spot the application
# layer misses rather than relying on it exclusively. Safe to enable now:
# every parent->child relationship that's actually deleted through the ORM
# (Client, Order) already declares `cascade="all, delete-orphan"`, so
# SQLAlchemy issues the child DELETEs before the parent's regardless of DB
# enforcement; the remaining non-cascaded FKs (Creator/Order->CreatorPayout,
# Creator->Script/Shoot/Video) are the ones this same part's audit added
# application-level 409 guards for (see creator_service.delete_creator,
# order_service.delete_order) specifically so this pragma would never fire
# on a path this app actually exercises. If it ever does fire on some path
# not yet covered by an explicit check, that's exactly the class of
# integrity bug this pragma exists to catch -- it will surface as a normal
# 409 via main.py's existing IntegrityError handler, never a raw 500.
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
