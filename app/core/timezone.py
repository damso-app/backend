from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def today_range_in_kst(now: datetime | None = None) -> tuple[datetime, datetime]:
    base_now = now or datetime.now(UTC)
    if base_now.tzinfo is None:
        base_now = base_now.replace(tzinfo=UTC)

    today = base_now.astimezone(KST).date()
    return kst_date_range(today)


def kst_date_range(day: date) -> tuple[datetime, datetime]:
    start_kst = datetime.combine(day, time.min, tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(UTC), end_kst.astimezone(UTC)
