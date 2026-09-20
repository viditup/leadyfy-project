"""
Shared pagination helper for list endpoints.
"""
from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

from fastapi import Query
from sqlalchemy import func
from sqlalchemy.orm import Query as SAQuery

from app.config import settings

T = TypeVar("T")


@dataclass
class PageParams:
    page: int = 1
    per_page: int = settings.DEFAULT_PAGE_SIZE


def page_params(
    page: int = Query(1, ge=1, description="1-indexed page number"),
    per_page: int = Query(
        settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE, description="Items per page"
    ),
) -> PageParams:
    return PageParams(page=page, per_page=per_page)


def paginate(query: SAQuery, params: PageParams) -> dict:
    """
    Applies OFFSET/LIMIT to a SQLAlchemy query without loading the full
    result set into memory, and returns a consistent envelope.
    """
    total = query.order_by(None).with_entities(func.count()).scalar() or 0
    items: Sequence = (
        query.offset((params.page - 1) * params.per_page).limit(params.per_page).all()
    )
    total_pages = (total + params.per_page - 1) // params.per_page if params.per_page else 0
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "per_page": params.per_page,
        "total_pages": total_pages,
    }
