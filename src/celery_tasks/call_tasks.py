import json
from datetime import datetime, timedelta
import logging

import telnyx
from celery import shared_task
from fastapi.encoders import jsonable_encoder

from src.database.cache import cache
from src.database.call_session import Action, CallSession
from src.database.db import get_db
from src.database.email import Email
from src.database.email_account import EmailAccount
from src.database.user import User
from src.libs.const import TELNYX_API_KEY
from src.libs.types import EmailFolder

telnyx.api_key = TELNYX_API_KEY

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


@shared_task(name="hangup_call")
def hangup_call(call_control_id: str):
    call = telnyx.Call.retrieve(call_control_id)
    call.hangup()


@shared_task(name="prepare_email_brief")
def prepare_email_brief(phone_number: str, call_control_id: str, call_session_id: str):
    with get_db() as db:
        user = db.query(User).filter(User.phone_number == phone_number).first()

        if user:
            new_emails = (
                db.query(Email)
                .filter()
                .join(EmailAccount, Email.email_account_id == EmailAccount.id)
                .filter(
                    Email.is_read == False,
                    Email.folder == EmailFolder.INBOX,
                    Email.date >= datetime.now() - timedelta(days=1),
                    EmailAccount.user_id == user.id,
                )
                .order_by(Email.created_at.desc())
                .all()
            )
            cache.set(
                f"call_control_id_{call_control_id}",
                json.dumps(
                    [
                        jsonable_encoder(
                            email.to_dict(
                                allowed_columns=[
                                    "id",
                                    "sender",
                                    "sender_name",
                                    "subject",
                                    "date",
                                    "summary",
                                    "snippet",
                                ]
                            )
                        )
                        for email in new_emails
                    ]
                ),
                ex=3600,
            )

            call_session = CallSession(
                user_id=user.id,
                call_control_id=call_control_id,
                follow_up_tasks=[],
            )
            db.add(call_session)
            db.commit()


@shared_task(name="follow_up_actions")
def follow_up_actions(call_control_id: str = None):
    with get_db() as db:
        call_sessions = (
            db.query(CallSession)
            .filter(CallSession.is_processed == False, CallSession.is_completed == False)
            .all()
        )
        logger.info(f"Found {len(call_sessions)} call sessions")
        if call_sessions:
            for call_session in call_sessions:
                logger.info(
                    f"Processing call session {call_session.id} with tasks {call_session.follow_up_tasks}"
                )
                call = telnyx.Call.retrieve(call_session.call_control_id)
                if not call["is_alive"]:
                    call_session.is_completed = True
                    if tasks := call_session.follow_up_tasks:
                        for task in tasks:
                            if Action(task["action"]) == Action.RESPOND_TO_EMAIL:
                                logger.info(f"Drafting response for email {task['email_id']}")
                                email = db.query(Email).get({"id": task["email_id"]})
                                if email:
                                    email.draft_response(task["email_body"], db)
                            elif Action(task["action"]) == Action.MARK_AS_UNREAD:
                                logger.info(f"Marking email {task['email_id']} as unread")
                                email = db.query(Email).get({"id": task["email_id"]})
                                if email:
                                    email.mark_as_unread(db)
                            elif Action(task["action"]) == Action.MARK_AS_READ:
                                logger.info(f"Marking email {task['email_id']} as read")
                                email = db.query(Email).get({"id": task["email_id"]})
                                if email:
                                    email.mark_as_read(db)
                    call_session.is_processed = True
                    db.add(call_session)
                    db.commit()
