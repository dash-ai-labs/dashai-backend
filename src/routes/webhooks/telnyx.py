import json
from fastapi import APIRouter, Depends, Request

from src.routes.middleware import check_secret_token
from src.database.db import get_db
from src.database.user import User
from src.celery_tasks.call_tasks import hangup_call, prepare_email_brief
from src.database.cache import cache
from src.libs.const import PHONE_NUMBER_NOT_FOUND_MESSAGE, TELNYX_API_KEY
import telnyx

router = APIRouter()

telnyx.api_key = TELNYX_API_KEY


@router.post("/telnyx/name")
async def telnyx_name_webhook(request: Request):
    body = await request.json()
    data = body["data"]
    payload = data["payload"]
    call_control_id = payload["call_control_id"]
    call_session_id = payload["call_session_id"]
    from_number = payload["from"]
    with get_db() as db:
        if name := cache.get(from_number):
            first_name = name.split(" ")[0]
            greeting_message = f"Hi {first_name}, this is Dash AI. Ready for your email brief?"
            prepare_email_brief.delay(from_number, call_control_id, call_session_id)
            return {"dynamic_variables": {"greeting_message": greeting_message}}
        elif user := db.query(User).filter(User.phone_number == from_number).first():
            first_name = user.name.split(" ")[0]
            greeting_message = f"Hi {first_name}, this is Dash AI. Ready for your email brief?"
            prepare_email_brief.delay(from_number, call_control_id, call_session_id)
            cache.set(from_number, user.name)
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


@router.get("/telnyx/emails")
async def telnyx_emails_webhook(request: Request, user=Depends(check_secret_token)):
    headers = request.headers
    if call_control_id := headers.get("call_control_id"):
        if emails := cache.get(f"call_control_id_{call_control_id}"):
            return {"emails": json.loads(emails)}
        else:
            return {"message": "No emails found"}
    else:
        return {"message": "Something went wrong. Please try again later."}
