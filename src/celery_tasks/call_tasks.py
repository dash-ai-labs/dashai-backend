import json
from celery import shared_task

from src.database.cache import cache
from src.database.email_account import EmailAccount
from src.database.email import Email
from src.database.call_session import CallSession
from src.database.db import get_db
from src.database.user import User
from src.libs.const import TELNYX_API_KEY
import telnyx

telnyx.api_key = TELNYX_API_KEY


@shared_task(name="hangup_call")
def hangup_call(call_control_id: str):
    call = telnyx.Call.retrieve(call_control_id)
    call.hangup()


@shared_task(name="prepare_email_brief")
def prepare_email_brief(phone_number: str, call_control_id: str, call_session_id: str):
    with get_db() as db:
        user = db.query(User).filter(User.phone_number == phone_number).first()

        if user:
            if (
                latest_call_session := db.query(CallSession)
                .filter(CallSession.user_id == user.id)
                .order_by(CallSession.created_at.desc())
                .first()
            ):
                new_emails = (
                    db.query(Email)
                    .join(EmailAccount, Email.email_account_id == EmailAccount.id)
                    .filter(
                        Email.date >= latest_call_session.created_at,
                        Email.is_read == False,
                        EmailAccount.user_id == user.id,
                    )
                    .all()
                )
                cache.set(
                    f"call_control_id_{call_control_id}",
                    json.dumps(
                        [
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
                            for email in new_emails
                        ]
                    ),
                    ex=3600,
                )

                if not cache.get(phone_number):
                    cache.set(phone_number, user.name)
            else:
                new_emails = (
                    db.query(Email)
                    .join(EmailAccount, Email.email_account_id == EmailAccount.id)
                    .filter(
                        Email.is_read == False,
                        EmailAccount.user_id == user.id,
                    )
                    .all()
                )
                cache.set(
                    f"call_control_id_{call_control_id}",
                    json.dumps(
                        [
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
                            for email in new_emails
                        ]
                    ),
                    ex=3600,
                )

            call_session = CallSession(
                user_id=user.id,
                call_control_id=call_control_id,
                call_session_id=call_session_id,
            )
            db.add(call_session)
            db.commit()
