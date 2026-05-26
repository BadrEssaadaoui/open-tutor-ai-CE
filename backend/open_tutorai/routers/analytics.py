"""
Analytics router for Open TutorAI.

Implements upstream issue #47:
"📊 Real-Time Analytics Dashboard for Tracking AI Learning and Feedback Impact"

All endpoints are admin-only and read-only. They aggregate over the existing
upstream Open WebUI ``feedback`` table plus the custom ``opentutorai_support``
table — no schema changes are required.

The router is mounted in ``open_tutorai.main`` under ``/api/v1``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, case, and_
from sqlalchemy.orm import Session

from open_webui.internal.db import get_db
from open_webui.models.feedbacks import Feedback
from open_webui.models.users import User
from open_webui.utils.auth import get_admin_user

from open_tutorai.models.database import Support

log = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

Range = Literal["24h", "7d", "30d", "90d", "all"]
Bucket = Literal["hour", "day", "week"]

_RANGE_TO_DELTA: dict[str, Optional[timedelta]] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "all": None,
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _cutoff(range_: Range) -> Optional[int]:
    """Return epoch-seconds cutoff for the requested range, or None for 'all'."""
    delta = _RANGE_TO_DELTA.get(range_)
    if delta is None:
        return None
    return int((datetime.now(tz=timezone.utc) - delta).timestamp())


def _bucket_expr(bucket: Bucket):
    """Truncate Feedback.created_at (epoch seconds) into a bucket boundary."""
    # SQLite has no DATE_TRUNC; floor-divide epoch seconds for portability.
    seconds = {"hour": 3600, "day": 86400, "week": 604800}[bucket]
    return (func.cast(Feedback.created_at, type_=func.Integer) / seconds) * seconds


def _slugify(value: str) -> str:
    return _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-") or "uncategorized"


def _rating(field: str = "rating"):
    """JSON extractor that works on Postgres + SQLite (Open WebUI ships both)."""
    return func.json_extract(Feedback.data, f"$.{field}")


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #


class SummaryResponse(BaseModel):
    range: Range
    total_feedbacks: int = Field(..., description="All feedback events in range")
    positive: int
    negative: int
    neutral: int
    corrections: int = Field(..., description="response_comparison events")
    distinct_users: int
    distinct_models: int
    positive_rate: float = Field(..., ge=0, le=1)
    delta_positive_rate: float = Field(
        ...,
        description="Change in positive_rate vs previous equal-length window (-1..1)",
    )


class TimeseriesPoint(BaseModel):
    bucket: int  # epoch seconds at bucket start
    total: int
    positive: int
    negative: int


class CorrectionsResponse(BaseModel):
    range: Range
    daily: list[TimeseriesPoint]
    top_categories: list[dict]  # [{category, count}]
    resolution_rate: float = Field(..., ge=0, le=1)


class ModelStat(BaseModel):
    model_id: str
    positive: int
    negative: int
    total: int
    score: float = Field(..., description="positive / max(total,1)")
    trajectory: list[TimeseriesPoint]


class ContributorStat(BaseModel):
    user_id: str
    name: Optional[str] = None
    role: Optional[str] = None
    count: int


class PedagogyStat(BaseModel):
    subject: str
    level: Optional[str] = None
    count: int
    positive_rate: float


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    range_: Range = Query("7d", alias="range"),
    user=Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> SummaryResponse:
    cutoff = _cutoff(range_)
    base = db.query(Feedback)
    if cutoff is not None:
        base = base.filter(Feedback.created_at >= cutoff)

    total = base.count()
    positive = base.filter(_rating() > 0).count()
    negative = base.filter(_rating() < 0).count()
    neutral = max(total - positive - negative, 0)
    corrections = base.filter(Feedback.type == "response_comparison").count()
    distinct_users = base.with_entities(Feedback.user_id).distinct().count()
    distinct_models = (
        base.with_entities(_rating("model_id")).distinct().count()
    )
    positive_rate = positive / total if total else 0.0

    # delta vs previous equal-length window
    delta_positive_rate = 0.0
    if cutoff is not None and _RANGE_TO_DELTA[range_] is not None:
        prev_cutoff = cutoff - int(_RANGE_TO_DELTA[range_].total_seconds())
        prev = db.query(Feedback).filter(
            and_(Feedback.created_at >= prev_cutoff, Feedback.created_at < cutoff)
        )
        prev_total = prev.count()
        prev_pos = prev.filter(_rating() > 0).count()
        prev_rate = prev_pos / prev_total if prev_total else 0.0
        delta_positive_rate = round(positive_rate - prev_rate, 4)

    return SummaryResponse(
        range=range_,
        total_feedbacks=total,
        positive=positive,
        negative=negative,
        neutral=neutral,
        corrections=corrections,
        distinct_users=distinct_users,
        distinct_models=distinct_models,
        positive_rate=round(positive_rate, 4),
        delta_positive_rate=delta_positive_rate,
    )


@router.get("/feedback-timeseries", response_model=list[TimeseriesPoint])
def get_feedback_timeseries(
    range_: Range = Query("30d", alias="range"),
    bucket: Bucket = Query("day"),
    user=Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[TimeseriesPoint]:
    cutoff = _cutoff(range_)
    b = _bucket_expr(bucket).label("bucket")
    rows = (
        db.query(
            b,
            func.count(Feedback.id).label("total"),
            func.sum(case((_rating() > 0, 1), else_=0)).label("positive"),
            func.sum(case((_rating() < 0, 1), else_=0)).label("negative"),
        )
        .filter(Feedback.created_at >= cutoff if cutoff else True)
        .group_by(b)
        .order_by(b)
        .all()
    )
    return [
        TimeseriesPoint(
            bucket=int(r.bucket or 0),
            total=int(r.total or 0),
            positive=int(r.positive or 0),
            negative=int(r.negative or 0),
        )
        for r in rows
    ]


@router.get("/corrections", response_model=CorrectionsResponse)
def get_corrections(
    range_: Range = Query("30d", alias="range"),
    user=Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> CorrectionsResponse:
    cutoff = _cutoff(range_)
    base = db.query(Feedback).filter(Feedback.type == "response_comparison")
    if cutoff is not None:
        base = base.filter(Feedback.created_at >= cutoff)

    # daily timeseries
    b = _bucket_expr("day").label("bucket")
    daily_rows = (
        base.with_entities(
            b,
            func.count(Feedback.id).label("total"),
            func.sum(case((_rating() > 0, 1), else_=0)).label("positive"),
            func.sum(case((_rating() < 0, 1), else_=0)).label("negative"),
        )
        .group_by(b)
        .order_by(b)
        .all()
    )
    daily = [
        TimeseriesPoint(
            bucket=int(r.bucket or 0),
            total=int(r.total or 0),
            positive=int(r.positive or 0),
            negative=int(r.negative or 0),
        )
        for r in daily_rows
    ]

    # category buckets — slug the free-text reason. Done in Python to stay
    # database-agnostic (json_extract behaves differently on PG vs SQLite).
    categories: dict[str, int] = {}
    resolved = 0
    seen = 0
    for f in base.all():
        seen += 1
        data = f.data or {}
        reason = data.get("reason") if isinstance(data, dict) else None
        if reason:
            resolved += 1
            categories[_slugify(reason)] = categories.get(_slugify(reason), 0) + 1

    top_categories = [
        {"category": k, "count": v}
        for k, v in sorted(categories.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]
    resolution_rate = resolved / seen if seen else 0.0

    return CorrectionsResponse(
        range=range_,
        daily=daily,
        top_categories=top_categories,
        resolution_rate=round(resolution_rate, 4),
    )


@router.get("/models", response_model=list[ModelStat])
def get_models(
    range_: Range = Query("30d", alias="range"),
    limit: int = Query(10, ge=1, le=50),
    user=Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[ModelStat]:
    cutoff = _cutoff(range_)
    model_expr = _rating("model_id").label("model_id")
    base = db.query(Feedback)
    if cutoff is not None:
        base = base.filter(Feedback.created_at >= cutoff)

    agg = (
        base.with_entities(
            model_expr,
            func.count(Feedback.id).label("total"),
            func.sum(case((_rating() > 0, 1), else_=0)).label("positive"),
            func.sum(case((_rating() < 0, 1), else_=0)).label("negative"),
        )
        .group_by(model_expr)
        .order_by(func.count(Feedback.id).desc())
        .limit(limit)
        .all()
    )

    results: list[ModelStat] = []
    b = _bucket_expr("day").label("bucket")
    for row in agg:
        if not row.model_id:
            continue
        traj_rows = (
            base.filter(_rating("model_id") == row.model_id)
            .with_entities(
                b,
                func.count(Feedback.id).label("total"),
                func.sum(case((_rating() > 0, 1), else_=0)).label("positive"),
                func.sum(case((_rating() < 0, 1), else_=0)).label("negative"),
            )
            .group_by(b)
            .order_by(b)
            .all()
        )
        results.append(
            ModelStat(
                model_id=str(row.model_id),
                positive=int(row.positive or 0),
                negative=int(row.negative or 0),
                total=int(row.total or 0),
                score=round(
                    (row.positive or 0) / max(int(row.total or 1), 1), 4
                ),
                trajectory=[
                    TimeseriesPoint(
                        bucket=int(t.bucket or 0),
                        total=int(t.total or 0),
                        positive=int(t.positive or 0),
                        negative=int(t.negative or 0),
                    )
                    for t in traj_rows
                ],
            )
        )
    return results


@router.get("/contributors", response_model=list[ContributorStat])
def get_contributors(
    range_: Range = Query("30d", alias="range"),
    limit: int = Query(10, ge=1, le=50),
    user=Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[ContributorStat]:
    cutoff = _cutoff(range_)
    base = db.query(Feedback)
    if cutoff is not None:
        base = base.filter(Feedback.created_at >= cutoff)
    rows = (
        base.with_entities(
            Feedback.user_id, func.count(Feedback.id).label("count")
        )
        .group_by(Feedback.user_id)
        .order_by(func.count(Feedback.id).desc())
        .limit(limit)
        .all()
    )
    user_ids = [r.user_id for r in rows if r.user_id]
    users_by_id = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(user_ids)).all()
    }
    return [
        ContributorStat(
            user_id=r.user_id,
            name=getattr(users_by_id.get(r.user_id), "name", None),
            role=getattr(users_by_id.get(r.user_id), "role", None),
            count=int(r.count or 0),
        )
        for r in rows
    ]


@router.get("/pedagogy", response_model=list[PedagogyStat])
def get_pedagogy(
    range_: Range = Query("30d", alias="range"),
    user=Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[PedagogyStat]:
    """Join feedback events to opentutorai_support via chat_id.

    For every Support row in range, count feedbacks linked to its chat and
    compute the share that are positive.
    """
    cutoff = _cutoff(range_)
    fb = db.query(Feedback)
    if cutoff is not None:
        fb = fb.filter(Feedback.created_at >= cutoff)

    chat_id_expr = func.json_extract(Feedback.meta, "$.chat_id").label("chat_id")
    sub_q = (
        fb.with_entities(
            chat_id_expr,
            func.count(Feedback.id).label("count"),
            func.sum(case((_rating() > 0, 1), else_=0)).label("positive"),
        )
        .group_by(chat_id_expr)
        .subquery()
    )

    rows = (
        db.query(
            Support.subject,
            Support.level,
            func.coalesce(func.sum(sub_q.c.count), 0).label("count"),
            func.coalesce(func.sum(sub_q.c.positive), 0).label("positive"),
        )
        .outerjoin(sub_q, sub_q.c.chat_id == Support.chat_id)
        .group_by(Support.subject, Support.level)
        .order_by(func.coalesce(func.sum(sub_q.c.count), 0).desc())
        .limit(20)
        .all()
    )

    out: list[PedagogyStat] = []
    for r in rows:
        total = int(r.count or 0)
        positive = int(r.positive or 0)
        out.append(
            PedagogyStat(
                subject=str(r.subject or "Unknown"),
                level=r.level,
                count=total,
                positive_rate=round(positive / total, 4) if total else 0.0,
            )
        )
    return out
