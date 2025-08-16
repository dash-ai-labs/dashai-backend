from celery import Celery
from dotenv import load_dotenv

from src.libs.const import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

load_dotenv()

celery = Celery(
    __name__,
)


celery.autodiscover_tasks(["src.celery_tasks.tasks", "src.celery_tasks.call_tasks"])
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_compression="zlib",
)
celery.conf.broker_url = CELERY_BROKER_URL
celery.conf.result_backend = CELERY_RESULT_BACKEND
celery.conf.beat_schedule = {
    "run-every-15-minutes": {
        "task": "get_new_emails",
        "schedule": 15 * 60,  # 15 minutes
    },
    "run-every-15-minutes-embed": {
        "task": "embed_new_emails",
        "schedule": 15 * 60,  # 15 minutes
    },
    "run-every-15-minutes-embed-attachments": {
        "task": "embed_new_attachments",
        "schedule": 15 * 60,  # 15 minutes
    },
    "run-every-15-minutes-follow-up-actions": {
        "task": "follow_up_actions",
        "schedule": 15 * 60,  # 15 minutes
    },
    "run-every-7-days-add-to-weekly-recap": {
        "task": "add_to_weekly_recap",
        "schedule": 60 * 60 * 24 * 7,  # 7 days
    },
    # "run-every-day-at-7am": {  # Updated task name
    #     "task": "get_new_transactions",
    #     "schedule": crontab(hour=7, minute=0),  # Run every day at 7 AM
    # },
}


def start_worker():
    """Start the Celery worker"""
    worker = celery.Worker(loglevel="info")
    worker.start()


def start_beat():
    """Start the Celery beat scheduler"""
    beat = celery.Beat(loglevel="info")
    beat.run()
