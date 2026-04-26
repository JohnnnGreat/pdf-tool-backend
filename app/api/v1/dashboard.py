from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardActivity, DashboardStats, HistoryFilters, HistoryPage
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return DashboardService(db).get_stats(current_user.id)


@router.get("/activity", response_model=DashboardActivity)
def get_activity(
    period: str = Query("week", pattern="^(day|week|month|year)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return DashboardService(db).get_activity(current_user.id, period)


@router.get("/history", response_model=HistoryPage)
def get_history(
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=100),
    search: str = Query(""),
    category: str = Query(""),
    status: str = Query(""),
    period: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = HistoryFilters(
        page=page,
        limit=limit,
        search=search,
        category=category,
        status=status,
        period=period,
    )
    return DashboardService(db).get_history(current_user.id, filters)
