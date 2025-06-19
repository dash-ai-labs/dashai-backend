from celery import shared_task

from src.database.db import get_db
from src.database.user import User
from src.libs.const import TELNYX_API_KEY
import telnyx

telnyx.api_key = TELNYX_API_KEY


@shared_task(name="hangup_call")
def hangup_call(call_control_id: str):
    call = telnyx.Call.retrieve(call_control_id)
    call.hangup()


@shared_task(name="load_email_brief")
def load_email_brief(phone_number: str, call_control_id: str, call_session_id: str):
    with get_db() as db:
        user = db.query(User).filter(User.phone_number == phone_number).first()
        if user:
            email_brief = user.email_brief
            if email_brief:
                email_brief.load()
