from fastapi import APIRouter, Depends, Request

from src.celery_tasks.call_tasks import hangup_call, load_email_brief
from src.database.cache import cache
from src.libs.const import PHONE_NUMBER_NOT_FOUND_MESSAGE, TELNYX_API_KEY
import telnyx

router = APIRouter()

telnyx.api_key = TELNYX_API_KEY


@router.post("/telnyx/name")
async def telnyx_name_webhook(request: Request, user=Depends(check_secret_token)):
    body = await request.json()
    data = body["data"]
    payload = data["payload"]
    call_control_id = payload["call_control_id"]
    call_session_id = payload["call_session_id"]
    from_number = payload["from"]
    if name := await cache.get(from_number):
        first_name = name.split(" ")[0]
        greeting_message = f"Hi {first_name}, this is Dash AI. Ready for your email brief?"

        load_email_brief.delay(from_number, call_control_id, call_session_id)

        return {"dynamic_variables": {"greeting_message": greeting_message}}
    else:
        call = telnyx.Call.retrieve(call_control_id)
        call.playback_start(
            audio_url=PHONE_NUMBER_NOT_FOUND_MESSAGE,
            overlay=False,
            stop="all",
        )
        hangup_call.apply_async(args=[call_control_id], countdown=8)
        return {"dynamic_variables": {"greeting_message": ""}}
