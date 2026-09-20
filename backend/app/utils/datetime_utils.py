from datetime import datetime, timezone


def as_utc(dt: datetime | None) -> datetime | None:
    """
    Normalize a datetime to aware-UTC.

    SQLite hands back *naive* datetimes for `DateTime(timezone=True))`
    columns regardless of the column definition (SQLAlchemy's SQLite dialect
    has no native timestamp-with-timezone type), while the app always writes
    aware UTC values (`datetime.now(timezone.utc)`). Comparing a naive value
    against an aware one raises `TypeError`, so every naive value coming out
    of the ORM is treated as UTC before comparison; already-aware values are
    converted to UTC for a consistent basis.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
