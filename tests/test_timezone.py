from datetime import UTC, date, datetime

from app.core.timezone import kst_date_range, today_range_in_kst


def test_kst_date_range_returns_utc_boundaries_for_korea_day() -> None:
    start, end = kst_date_range(date(2026, 7, 6))

    assert start == datetime(2026, 7, 5, 15, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


def test_today_range_in_kst_uses_korea_date_not_utc_date() -> None:
    start, end = today_range_in_kst(datetime(2026, 7, 5, 16, 0, tzinfo=UTC))

    assert start == datetime(2026, 7, 5, 15, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
