from pydantic import BaseModel
from typing import Literal


Period = Literal["day", "week", "month", "year"]


class CategoryUsage(BaseModel):
    category: str
    label:    str
    count:    int
    pct:      float


class DashboardStats(BaseModel):
    files_processed:    int
    tools_used:         int
    storage_saved_bytes:int
    requests_today:     int
    trend_files_pct:    float
    trend_tools_pct:    float
    trend_storage_pct:  float
    trend_requests_pct: float
    category_usage:     list[CategoryUsage]


class DashboardActivity(BaseModel):
    labels: list[str]
    counts: list[int]


class HistoryFilters(BaseModel):
    page:     int   = 1
    limit:    int   = 15
    search:   str   = ""
    category: str   = ""
    status:   str   = ""
    period:   str   = ""


class HistoryPage(BaseModel):
    items: list
    total: int
    page:  int
    pages: int
