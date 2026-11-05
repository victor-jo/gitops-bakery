# Converts KST schedules into the 6-field UTC cron expressions KFP recurring runs take, and creates a recurring run only once per name
from datetime import timedelta

KST_OFFSET = timedelta(hours=9)


def weekly_cron_utc(weekday: int, hour: int, minute: int = 0) -> str:
    """Cron 'sec min hour day-of-month month day-of-week' in UTC for a weekly KST time; weekday 0 is Sunday."""
    shifted = (weekday * 24 * 60 + hour * 60 + minute - KST_OFFSET // timedelta(minutes=1)) % (7 * 24 * 60)
    day, rest = divmod(shifted, 24 * 60)
    return f"0 {rest % 60} {rest // 60} * * {day}"


def daily_cron_utc(hour: int, minute: int = 0) -> str:
    """Cron in UTC for a daily KST time."""
    shifted = (hour * 60 + minute - KST_OFFSET // timedelta(minutes=1)) % (24 * 60)
    return f"0 {shifted % 60} {shifted // 60} * * *"


# Daily 05:00 KST is 20:00 UTC; Monday 06:00 KST is Sunday 21:00 UTC; Monday 07:00 KST is Sunday 22:00 UTC
CATALOG_CRON = daily_cron_utc(hour=5)
TRAINING_CRON = weekly_cron_utc(weekday=1, hour=6)
MONITORING_CRON = weekly_cron_utc(weekday=1, hour=7)
CRONS = {"movie-catalog": CATALOG_CRON, "movie-recommender-training": TRAINING_CRON, "movie-recommender-monitoring": MONITORING_CRON}


def list_all_recurring_runs(client) -> list:
    """Every recurring run, following next_page_token until the server has no more pages."""
    runs, token = [], ""
    while True:
        page = client.list_recurring_runs(page_token=token, page_size=100)
        runs += page.recurring_runs or []
        token = page.next_page_token
        if not token:
            return runs


def schedule_recurring(client, job_name: str, **create_args):
    """Create the recurring run first, then delete older ones with the same name, so a failed create keeps the old schedule."""
    new = client.create_recurring_run(job_name=job_name, **create_args)
    for old in list_all_recurring_runs(client):
        if old.display_name == job_name and old.recurring_run_id != new.recurring_run_id:
            client.delete_recurring_run(old.recurring_run_id)
    return new
