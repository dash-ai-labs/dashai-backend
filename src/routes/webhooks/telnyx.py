from fastapi import APIRouter, Depends, Request
import requests

from src.celery_tasks.call_tasks import hangup_call
from src.libs.const import PHONE_NUMBER_NOT_FOUND_MESSAGE, TELNYX_API_KEY
from src.routes.middleware import check_secret_token
import telnyx

router = APIRouter()

telnyx.api_key = TELNYX_API_KEY


@router.post("/telnyx/name")
async def telnyx_name_webhook(request: Request, user=Depends(check_secret_token)):
    body = await request.json()
    data = body["data"]
    call_control_id = data["payload"]["call_control_id"]
    call = telnyx.Call.retrieve(call_control_id)
    call.playback_start(
        audio_url=PHONE_NUMBER_NOT_FOUND_MESSAGE,
        overlay=False,
        stop="all",
    )
    hangup_call.apply_async(args=[call_control_id], countdown=8)
    return {"dynamic_variables": {"greeting_message": ""}}
