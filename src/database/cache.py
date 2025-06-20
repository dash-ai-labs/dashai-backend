import redis

from src.libs.const import CELERY_BROKER_URL

cache = redis.from_url(CELERY_BROKER_URL)
