import os
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import pytz

from services.database import ip_credits_collection

load_dotenv()
logger = logging.getLogger("voicera.scheduler")

# Read default credits; fallback to 10 if not set to keep the job resilient
DEFAULT_CREDITS = int(os.getenv("DEFAULT_CREDITS", "10"))

_scheduler: Optional[AsyncIOScheduler] = None


async def reset_credits_job() -> None:
    """Reset all IP credits to DEFAULT_CREDITS and update last_used to now (UTC)."""
    try:
        now_utc_ts = int(datetime.now(tz=timezone.utc).timestamp())
        result = await ip_credits_collection.update_many(
            {},
            {"$set": {"credits": DEFAULT_CREDITS, "last_used": now_utc_ts}},
        )
        logger.info(
            "Daily credit reset complete: matched=%s modified=%s",
            getattr(result, "matched_count", None),
            getattr(result, "modified_count", None),
        )
    except Exception as e:
        logger.exception("Daily credit reset failed: %s", e)


def start_scheduler() -> None:
    """Start an AsyncIO scheduler with a daily 04:00 IST job."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    ist = pytz.timezone("Asia/Kolkata")
    _scheduler = AsyncIOScheduler(timezone=ist)
    _scheduler.add_job(
        reset_credits_job,
        trigger=CronTrigger(hour=4, minute=0, timezone=ist),
        id="daily_credit_reset",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,  # 1 hour grace if the app was down at 04:00
    )
    _scheduler.start()
    logger.info("Scheduler started with daily credit reset at 04:00 IST")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
