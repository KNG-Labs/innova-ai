import os

from celery import Celery

redis_url = os.environ["REDIS_URL"]

celery_app = Celery("innova", broker=redis_url)

celery_app.conf.update(
    task_default_queue="innova.lead_delivery",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
)
