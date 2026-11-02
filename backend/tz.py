"""Timezone helpers. Everything is stored as naive UTC; the business timezone
is used for display, message text, business hours and daily report buckets."""
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo


def tzinfo(name: str):
    try:
        return ZoneInfo(name or "Asia/Dubai")
    except Exception:
        return ZoneInfo("Asia/Dubai")


def utcnow() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def to_utc_naive(dt: datetime) -> datetime:
    """Accept aware or naive datetimes; return naive UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def to_local(dt: datetime, tz_name: str) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(tzinfo(tz_name))


def local_to_utc(local_dt: datetime, tz_name: str) -> datetime:
    return local_dt.replace(tzinfo=tzinfo(tz_name)).astimezone(timezone.utc).replace(tzinfo=None)


def local_day_bounds(d: date, tz_name: str):
    start = local_to_utc(datetime(d.year, d.month, d.day), tz_name)
    end = local_to_utc(datetime(d.year, d.month, d.day) + timedelta(days=1), tz_name)
    return start, end


def local_today(tz_name: str) -> date:
    return to_local(utcnow(), tz_name).date()


def fmt_date(dt: datetime, tz_name: str) -> str:
    return to_local(dt, tz_name).strftime("%A, %d %B %Y")


def fmt_time(dt: datetime, tz_name: str) -> str:
    return to_local(dt, tz_name).strftime("%I:%M %p").lstrip("0")


def fmt_datetime(dt: datetime, tz_name: str) -> str:
    return f"{fmt_date(dt, tz_name)} at {fmt_time(dt, tz_name)}"
