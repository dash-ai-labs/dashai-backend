from enum import Enum
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from src.celery_tasks.tasks import get_new_emails, mark_emails_as_shown
from src.database import Contact, Email, EmailAccount, EmailLabel, VectorDB, get_db
from src.libs.types import EmailData, EmailFolder
from src.routes.middleware import get_user_id

router = APIRouter()
pinecone = VectorDB()


class ActionType(Enum):
    archive = "archive"
    delete = "delete"
    unread = "unread"
    read = "read"
    star = "star"
    spam = "spam"
    inbox = "inbox"


class LabelActionType(Enum):
    add = "add"
    remove = "remove"


@router.get("/user/{user_id}/emails/{folder}/count")
async def get_emails_count(
    user_id: str,
    folder: EmailFolder,
    user=Depends(get_user_id),
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            return (
                db.query(Email)
                .join(EmailAccount, Email.email_account_id == EmailAccount.id)
                .filter(Email.folder == folder, EmailAccount.user_id == user_id)
                .count()
            )
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/user/{user_id}/emails")
async def get_emails(
    request: Request,
    user_id: str,
    account: str = Query(default=""),
    filter_is_read: Optional[bool] = Query(default=None, alias="filter[is_read]"),
    folder: Optional[EmailFolder] = Query(default=EmailFolder.INBOX),
    limit: int = Query(default=30),
    page: int = Query(default=1),
    user=Depends(get_user_id),
):  # -> dict[str, Any]:

    if user_id == user.get("user_id"):
        with get_db() as db:
            get_new_emails.delay(user_id)
            if account:
                email_account = (
                    db.query(EmailAccount)
                    .filter(
                        EmailAccount.email == account,
                        EmailAccount.user_id == user_id,
                    )
                    .first()
                )
                if not email_account:
                    raise HTTPException(status_code=404, detail="Email account not found")

                # Get total count for pagination
                query = db.query(Email).filter(
                    Email.email_account_id == email_account.id,
                    Email.folder == folder,
                )

                if filter_is_read is not None:
                    query = query.filter(Email.is_read == filter_is_read)

                total_count = query.count()

                email_query = db.query(Email).filter(
                    Email.email_account_id == email_account.id,
                    Email.folder == folder,
                )

                if filter_is_read is not None:
                    email_query = email_query.filter(Email.is_read == filter_is_read)

                emails = (
                    email_query.order_by(Email.date.desc())
                    .limit(limit)
                    .offset((page - 1) * limit)
                    .all()
                )
            else:
                email_account_ids = [
                    id_tuple[0]
                    for id_tuple in db.query(EmailAccount.id)
                    .filter(EmailAccount.user_id == user_id)
                    .values(EmailAccount.id)
                ]

                # Get total count for pagination
                query = db.query(Email).filter(
                    Email.email_account_id.in_(email_account_ids), Email.folder == folder
                )

                if filter_is_read is not None:
                    query = query.filter(Email.is_read == filter_is_read)

                total_count = query.count()

                email_query = db.query(Email).filter(
                    Email.email_account_id.in_(email_account_ids), Email.folder == folder
                )
                if filter_is_read is not None:
                    email_query = email_query.filter(Email.is_read == filter_is_read)

                emails: list[Email] = (
                    email_query.order_by(Email.date.desc())
                    .limit(limit)
                    .offset((page - 1) * limit)
                    .all()
                )

                mark_emails_as_shown.delay([email.id for email in emails])

            # Check if we've reached the end of the records
            end = (page - 1) * limit + len(emails) >= total_count

            return {
                "emails": [email.to_dict() for email in emails],
                "end": end,
                "total_count": total_count,
            }

    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/user/{user_id}/email")
async def get_email(
    request: Request, user_id: str, id: str = Query(...), user=Depends(get_user_id)
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            email = db.query(Email).filter(Email.id == id).first()
            if not email:
                raise HTTPException(status_code=404, detail="Email not found")
            return email.to_dict()
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/user/{user_id}/email/{email_id}/content")
async def get_email_content(
    request: Request, user_id: str, email_id: str, user=Depends(get_user_id)
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            email = (
                db.query(Email)
                .filter(Email.email_id == email_id, EmailAccount.user_id == user_id)
                .first()
            )

            # increment score by 1 if email is opened
            contact = db.query(Contact).filter(Contact.id == id).first()
            contact.increment_score(db, 2)

            return HTMLResponse(content=email.sanitized_content(request))
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/user/{user_id}/email/{email_id}/{action}")
async def modify_email(
    request: Request,
    user_id: str,
    email_id: str,
    action: ActionType,
    user=Depends(get_user_id),
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            email = db.query(Email).filter(Email.email_id == email_id).first()
            if email and str(email.email_account.user_id) == user_id:
                if action == ActionType.read:
                    e = await email.mark_as_read(db)
                elif action == ActionType.unread:
                    e = await email.mark_as_unread(db)
                elif action == ActionType.archive:
                    e = await email.archive(db)
                elif action == ActionType.delete:
                    e = await email.delete(db)
                elif action == ActionType.inbox:
                    e = await email.move_to_inbox(db)
                elif action == ActionType.spam:
                    e = await email.move_to_spam(db)
                e = await e.sync_from_web(db)
                return e.to_dict()
            else:
                raise HTTPException(status_code=404, detail="Email not found")
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/user/{user_id}/email")
async def send_email(
    request: Request, user_id: str, email: EmailData = Body(...), user=Depends(get_user_id)
):
    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")

        email_account = (
            db.query(EmailAccount)
            .filter(EmailAccount.user_id == user_id, EmailAccount.email == email.from_addr)
            .first()
        )

        if not email_account:
            raise HTTPException(
                status_code=404, detail="Email account not found for the given sender address"
            )

        res = await email_account.send_email(email, db)

        if res:
            # Inrement score of contact by 1 if user sends an email to them
            contacts = email.to  # List of recipient email addresses
            for recipient_email in contacts:
                contact = db.query(Contact).filter(Contact.email_address == recipient_email).first()
                contact.increment_score(db, 3)

            return {"message": "Email sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")


@router.get("/user/{user_id}/email/chat")
async def chat_with_email(
    request: Request,
    user_id: str,
    query: str = Query(...),
    user=Depends(get_user_id),
):

    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")

        return StreamingResponse(pinecone.chat(query, 50, user_id), media_type="application/json")


@router.get("/user/{user_id}/email/search")
async def search_email(
    request: Request,
    user_id: str,
    query: str = Query(...),
    user=Depends(get_user_id),
):
    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")

        res = pinecone.query(query, 20, user_id)
        email_ids = [match["metadata"]["id"] for match in res["matches"]]
        emails = db.query(Email).filter(Email.email_id.in_(email_ids)).all()
        return [email.to_dict() for email in emails]


@router.post("/user/{user_id}/email/{email_id}/label/{label_id}/{action}")
async def email_label_action(
    request: Request,
    user_id: str,
    email_id: str,
    label_id: str,
    action: LabelActionType,
    user=Depends(get_user_id),
):
    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")

        email = (
            db.query(Email)
            .filter(Email.email_id == email_id, EmailAccount.user_id == user_id)
            .first()
        )
        label = (
            db.query(EmailLabel)
            .filter(EmailLabel.id == label_id, EmailLabel.user_id == user_id)
            .first()
        )
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        if not label:
            raise HTTPException(status_code=404, detail="Label not found")

        if action == LabelActionType.add:
            if label not in email.email_labels:
                email.email_labels.append(label)
        elif action == LabelActionType.remove:
            if label in email.email_labels:
                email.email_labels.remove(label)
        db.add(email)
        db.commit()
        return email.to_dict()
