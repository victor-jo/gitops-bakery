# Converts the weekly Monday 07:00 KST schedule into the 6-field UTC cron expression KFP recurring runs take
from datetime import timedelta

KST_OFFSET = timedelta(hours=9)


def weekly_cron_utc(weekday: int, hour: int, minute: int = 0) -> str:
    """Cron 'sec min hour day-of-month month day-of-week' in UTC for a weekly KST time; weekday 0 is Sunday."""
    shifted = (weekday * 24 * 60 + hour * 60 + minute - KST_OFFSET // timedelta(minutes=1)) % (7 * 24 * 60)
    day, rest = divmod(shifted, 24 * 60)
    return f"0 {rest % 60} {rest // 60} * * {day}"


# Monday 07:00 KST is Sunday 22:00 UTC
WEEKLY_CRON = weekly_cron_utc(weekday=1, hour=7)
