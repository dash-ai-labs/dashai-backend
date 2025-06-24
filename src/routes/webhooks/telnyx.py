import json

import telnyx
from fastapi import APIRouter, Body, Depends, Request

from src.celery_tasks.call_tasks import hangup_call, prepare_email_brief
from src.database.cache import cache
from src.database.call_session import Action, CallSession, FollowUpTask
from src.database.db import get_db
from src.database.user import User
from src.libs.const import PHONE_NUMBER_NOT_FOUND_MESSAGE, TELNYX_API_KEY
from src.routes.middleware import check_secret_token

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
            name = name.decode("utf-8") if isinstance(name, bytes) else name
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
async def telnyx_emails_webhook(request: Request, call_control_id=Depends(check_secret_token)):
    if emails := cache.get(f"call_control_id_{call_control_id}"):
        emails = emails.decode("utf-8") if isinstance(emails, bytes) else emails
        return {"emails": json.loads(emails)}
    else:
        return {"message": "No emails found"}


@router.post("/telnyx/draft_email")
async def telnyx_draft_email_webhook(
    request: Request, data=Body(None), call_control_id=Depends(check_secret_token)
):
    email_id = data["email_id"]
    body = data["body"]
    with get_db() as db:
        if (
            call_session := db.query(CallSession)
            .filter(CallSession.call_control_id == call_control_id)
            .first()
        ):
            draft_response_task = FollowUpTask(
                email_id=email_id,
                email_body=body,
                action=Action.RESPOND_TO_EMAIL,
            )
            call_session.follow_up_tasks.append(draft_response_task.to_dict())
            db.add(call_session)
            db.commit()
            return {"message": "Draft email saved"}
    return {"message": "Something went wrong. Please try again later."}


@router.post("/telnyx/mark_as_read")
async def telnyx_mark_as_read_webhook(
    request: Request, data=Body(None), call_control_id=Depends(check_secret_token)
):
    email_id = data["email_id"]
    print("email_id", email_id, call_control_id)

    try:
        with get_db() as db:
            if (
                call_session := db.query(CallSession)
                .filter(CallSession.call_control_id == call_control_id)
                .first()
            ):
                draft_response_task = FollowUpTask(
                    email_id=email_id,
                    action=Action.MARK_AS_READ,
                )
                call_session.follow_up_tasks.append(draft_response_task.to_dict())
                db.add(call_session)
                db.commit()
                return {"message": "Email marked as read"}
    except Exception as e:
        print("Error marking email as read: ", e)
        return {"message": "Something went wrong. Please try again later."}


@router.post("/telnyx/mark_as_unread")
async def telnyx_mark_as_unread_webhook(
    request: Request, data=Body(None), call_control_id=Depends(check_secret_token)
):
    email_id = data["email_id"]
    try:
        with get_db() as db:
            if (
                call_session := db.query(CallSession)
                .filter(CallSession.call_control_id == call_control_id)
                .first()
            ):
            draft_response_task = FollowUpTask(
                email_id=email_id,
                action=Action.MARK_AS_UNREAD,
            )
            call_session.follow_up_tasks.append(draft_response_task.to_dict())
            db.add(call_session)
            db.commit()
            return {"message": "Email marked as unread"}
    except Exception as e:
        print("Error marking email as unread: ", e)
        return {"message": "Something went wrong. Please try again later."}
