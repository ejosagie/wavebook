"""Ad tracking links and analytics for the mobile app.

Owners copy a tracking link per platform (?utm_source=...) and paste it into
their ad campaign. Visits and ad-sourced bookings are aggregated here, reusing
the same logic as the browser portal.
"""

from fastapi import APIRouter, Depends, Query

from ..config import settings
from ..deps import get_current_business
from .portal import _analytics, _analytics_window

router = APIRouter(prefix="/api/ads", tags=["ads"])


@router.get("/links")
def ad_links(business: dict = Depends(get_current_business)):
    return [
        {
            "key": key,
            "label": label,
            "url": f"https://{business['slug']}.{settings.PUBLIC_BASE_DOMAIN}/?utm_source={key}",
        }
        for key, label in settings.AD_SOURCES.items()
    ]


@router.get("/analytics")
def ads_analytics(
    range: str = Query(default="7d"),
    from_date: str = Query(default=""),
    to_date: str = Query(default=""),
    platform: str = Query(default="all"),
    page: int = Query(default=1),
    business: dict = Depends(get_current_business),
):
    from_dt, to_dt = _analytics_window(range, from_date, to_date)
    source = "" if platform.strip().lower() == "all" else platform.strip().lower()
    data = _analytics(business["id"], from_dt, to_dt, source, page=page)
    data["range"] = range
    data["from"] = from_dt[:10]
    data["to"] = to_dt[:10]
    data["platform"] = platform
    return data
