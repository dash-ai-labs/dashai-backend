from celery import shared_task

from src.libs.const import TELNYX_API_KEY
import telnyx

telnyx.api_key = TELNYX_API_KEY


@shared_task(name="hangup_call")
def hangup_call(call_control_id: str):
    call = telnyx.Call.retrieve(call_control_id)
    call.hangup()
