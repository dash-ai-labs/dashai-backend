from enum import Enum
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import and_, desc

from src.database import Email, EmailAccount, EmailData, EmailLabel, VectorDB, get_db
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


class LabelActionType(Enum):
    add = "add"
    remove = "remove"


@router.get("/user/{user_id}/emails")
async def get_emails(
    request: Request,
    user_id: str,
    account: str = Query(default=""),
    filter: Optional[str] = Query(default="INBOX"),
    limit: int = Query(default=30),
    page: int = Query(default=1),
    user=Depends(get_user_id),
):
    labels = filter.split(",")
    if user_id == user.get("user_id"):
        with get_db() as db:
            if account:
                email_account = (
                    db.query(EmailAccount)
                    .filter(EmailAccount.email == account, EmailAccount.user_id == user_id)
                    .first()
                )
                if not email_account:
                    raise HTTPException(status_code=404, detail="Email account not found")

                # Get total count for pagination
                total_count = (
                    db.query(Email)
                    .filter(
                        Email.email_account_id == email_account.id,
                        and_(*(Email.labels.any(label) for label in labels)),
                    )
                    .count()
                )

                emails: list[Email] = (
                    db.query(Email)
                    .filter(
                        Email.email_account_id == email_account.id,
                        and_(*(Email.labels.any(label) for label in labels)),
                    )
                    .order_by(desc(Email.date))
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
                total_count = (
                    db.query(Email)
                    .filter(
                        Email.email_account_id.in_(email_account_ids),
                        and_(*(Email.labels.any(label) for label in labels)),
                    )
                    .count()
                )

                emails: list[Email] = (
                    db.query(Email)
                    .filter(
                        Email.email_account_id.in_(email_account_ids),
                        and_(*(Email.labels.any(label) for label in labels)),
                    )
                    .order_by(Email.date.desc())
                    .limit(limit)
                    .offset((page - 1) * limit)
                    .all()
                )

            # Check if we've reached the end of the records
            end = (page - 1) * limit + len(emails) >= total_count

            return {"emails": [email.to_dict() for email in emails], "end": end}

    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/user/{user_id}/email/{email_id}")
async def get_email(request: Request, user_id: str, email_id: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        with get_db() as db:
            email = db.query(Email).filter(Email.id == email_id).first()
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
                    e = email.mark_as_read()
                elif action == ActionType.unread:
                    e = email.mark_as_unread()
                elif action == ActionType.archive:
                    e = email.archive()
                elif action == ActionType.delete:
                    e = email.delete()
                e = e.sync_from_web(db)
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

        res = email_account.send_email(email)
        if res:
            return {"message": "Email sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")


@router.get("/user/{user_id}/email/chat")
async def chat_email(
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
