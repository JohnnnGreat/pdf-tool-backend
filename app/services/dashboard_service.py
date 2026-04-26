from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from app.models.job import ProcessingJob
from app.schemas.dashboard import (
    CategoryUsage,
    DashboardActivity,
    DashboardStats,
    HistoryFilters,
    HistoryPage,
)
from app.schemas.job import JobResponse

CATEGORY_LABELS: dict[str, str] = {
    "pdf":       "PDF Tools",
    "convert":   "Convert",
    "image":     "Image",
    "ocr":       "OCR",
    "security":  "Security",
    "signature": "Sign & Stamp",
    "document":  "Documents",
    "generator": "Generators",
    "utility":   "Utilities",
    "batch":     "Batch",
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _pct_change(current: int | float, previous: int | float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    #  Stats                                                               #
    # ------------------------------------------------------------------ #

    def get_stats(self, user_id: int) -> DashboardStats:
        now = datetime.utcnow()

        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end   = this_month_start
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
        today_start      = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start  = today_start - timedelta(days=1)

        def success_q(start: datetime, end: datetime | None = None):
            q = self.db.query(ProcessingJob).filter(
                ProcessingJob.user_id == user_id,
                ProcessingJob.status  == "success",
                ProcessingJob.created_at >= start,
            )
            if end:
                q = q.filter(ProcessingJob.created_at < end)
            return q

        # ── This month ──────────────────────────────────────────────────
        files_this  = success_q(this_month_start).count()
        tools_this  = (
            self.db.query(func.count(distinct(ProcessingJob.tool_slug)))
            .filter(
                ProcessingJob.user_id  == user_id,
                ProcessingJob.status   == "success",
                ProcessingJob.created_at >= this_month_start,
            )
            .scalar() or 0
        )
        storage_this = (
            self.db.query(
                func.coalesce(
                    func.sum(ProcessingJob.file_size_bytes - ProcessingJob.output_size_bytes), 0
                )
            )
            .filter(
                ProcessingJob.user_id  == user_id,
                ProcessingJob.status   == "success",
                ProcessingJob.created_at >= this_month_start,
                ProcessingJob.output_size_bytes.isnot(None),
                ProcessingJob.output_size_bytes < ProcessingJob.file_size_bytes,
            )
            .scalar() or 0
        )
        requests_today = (
            self.db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == user_id, ProcessingJob.created_at >= today_start)
            .count()
        )

        # ── Last month (trend baseline) ──────────────────────────────────
        files_last   = success_q(last_month_start, last_month_end).count()
        tools_last   = (
            self.db.query(func.count(distinct(ProcessingJob.tool_slug)))
            .filter(
                ProcessingJob.user_id  == user_id,
                ProcessingJob.status   == "success",
                ProcessingJob.created_at >= last_month_start,
                ProcessingJob.created_at <  last_month_end,
            )
            .scalar() or 0
        )
        storage_last = (
            self.db.query(
                func.coalesce(
                    func.sum(ProcessingJob.file_size_bytes - ProcessingJob.output_size_bytes), 0
                )
            )
            .filter(
                ProcessingJob.user_id  == user_id,
                ProcessingJob.status   == "success",
                ProcessingJob.created_at >= last_month_start,
                ProcessingJob.created_at <  last_month_end,
                ProcessingJob.output_size_bytes.isnot(None),
                ProcessingJob.output_size_bytes < ProcessingJob.file_size_bytes,
            )
            .scalar() or 0
        )
        requests_yesterday = (
            self.db.query(ProcessingJob)
            .filter(
                ProcessingJob.user_id  == user_id,
                ProcessingJob.created_at >= yesterday_start,
                ProcessingJob.created_at <  today_start,
            )
            .count()
        )

        # ── Category breakdown ───────────────────────────────────────────
        rows = (
            self.db.query(ProcessingJob.category, func.count().label("cnt"))
            .filter(
                ProcessingJob.user_id  == user_id,
                ProcessingJob.status   == "success",
                ProcessingJob.created_at >= this_month_start,
            )
            .group_by(ProcessingJob.category)
            .order_by(func.count().desc())
            .all()
        )
        total_jobs = sum(r.cnt for r in rows) or 1
        category_usage = [
            CategoryUsage(
                category=r.category,
                label=CATEGORY_LABELS.get(r.category, r.category.capitalize()),
                count=r.cnt,
                pct=round((r.cnt / total_jobs) * 100, 1),
            )
            for r in rows[:6]
        ]

        return DashboardStats(
            files_processed=files_this,
            tools_used=tools_this,
            storage_saved_bytes=int(storage_this),
            requests_today=requests_today,
            trend_files_pct=_pct_change(files_this,        files_last),
            trend_tools_pct=_pct_change(tools_this,        tools_last),
            trend_storage_pct=_pct_change(storage_this,    storage_last),
            trend_requests_pct=_pct_change(requests_today, requests_yesterday),
            category_usage=category_usage,
        )

    # ------------------------------------------------------------------ #
    #  Activity chart                                                      #
    # ------------------------------------------------------------------ #

    def get_activity(self, user_id: int, period: str) -> DashboardActivity:
        now = datetime.utcnow()

        if period == "day":
            start  = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
            n      = 24
            labels = [f"{(start + timedelta(hours=i)).hour:02d}h" for i in range(n)]
            def bucket(dt: datetime) -> int:
                return max(0, min(n - 1, int((dt - start).total_seconds() // 3600)))

        elif period == "week":
            start  = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
            n      = 7
            labels = [DAY_NAMES[(start + timedelta(days=i)).weekday()] for i in range(n)]
            def bucket(dt: datetime) -> int:
                return max(0, min(n - 1, (dt.date() - start.date()).days))

        elif period == "month":
            start  = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
            n      = 30
            labels = [str((start + timedelta(days=i)).day) for i in range(n)]
            def bucket(dt: datetime) -> int:
                return max(0, min(n - 1, (dt.date() - start.date()).days))

        else:  # year
            months = []
            for i in range(11, -1, -1):
                m = now.month - i
                y = now.year
                while m <= 0:
                    m += 12
                    y -= 1
                months.append((y, m))
            start  = datetime(months[0][0], months[0][1], 1)
            n      = 12
            labels = [MONTH_NAMES[m - 1] for _, m in months]
            month_index = {(y, m): i for i, (y, m) in enumerate(months)}
            def bucket(dt: datetime) -> int:  # type: ignore[misc]
                return month_index.get((dt.year, dt.month), -1)

        rows = (
            self.db.query(ProcessingJob.created_at)
            .filter(
                ProcessingJob.user_id  == user_id,
                ProcessingJob.status   == "success",
                ProcessingJob.created_at >= start,
            )
            .all()
        )

        counts: list[int] = [0] * n
        for (created_at,) in rows:
            b = bucket(created_at)
            if 0 <= b < n:
                counts[b] += 1

        return DashboardActivity(labels=labels, counts=counts)

    # ------------------------------------------------------------------ #
    #  History                                                             #
    # ------------------------------------------------------------------ #

    def get_history(self, user_id: int, filters: HistoryFilters) -> HistoryPage:
        from sqlalchemy import or_

        q = (
            self.db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == user_id)
        )

        if filters.search:
            term = f"%{filters.search}%"
            q = q.filter(
                or_(
                    ProcessingJob.filename.ilike(term),
                    ProcessingJob.tool_name.ilike(term),
                )
            )
        if filters.category:
            q = q.filter(ProcessingJob.category == filters.category)
        if filters.status:
            q = q.filter(ProcessingJob.status == filters.status)
        if filters.period:
            period_start = self._period_start(filters.period)
            if period_start:
                q = q.filter(ProcessingJob.created_at >= period_start)

        total = q.count()
        page  = max(1, filters.page)
        limit = max(1, min(100, filters.limit))
        pages = max(1, (total + limit - 1) // limit)

        jobs = (
            q.order_by(ProcessingJob.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        return HistoryPage(
            items=[JobResponse.model_validate(j) for j in jobs],
            total=total,
            page=page,
            pages=pages,
        )

    @staticmethod
    def _period_start(period: str) -> datetime | None:
        now = datetime.utcnow()
        match period:
            case "day":   return now.replace(hour=0, minute=0, second=0, microsecond=0)
            case "week":  return (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
            case "month": return (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
            case "year":  return datetime(now.year, 1, 1)
            case _:       return None
