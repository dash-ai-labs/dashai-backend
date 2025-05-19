from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.database import User, Settings
from src.database.db import get_db
from src.database.vectory_db import VectorDB
from src.routes.middleware import get_user_id
from src.libs.email_preferences import EMAIL_COMPOSER_PROMPTS

router = APIRouter()
pinecone = VectorDB()


@router.post("/user/{user_id}/suggestion")
async def create_suggestion(
    user_id: str,
    email_id: Optional[list[str]] = Body(None),
    subject: Optional[str] = Body(None),
    body: Optional[str] = Body(None),
    writing_style: Optional[str] = Body(None),
    user=Depends(get_user_id),
):
    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")
        user = db.query(User).filter(User.id == user_id).first()

        # Get all settings for all the user's email accounts
        settings_list = []
        if user and user.email_accounts:
            email_account_ids = [account.id for account in user.email_accounts]
            settings_list = (
                db.query(Settings).filter(Settings.email_account_id.in_(email_account_ids)).all()
            )

        # You can either use the first settings, or handle multiple settings as needed
        settings = settings_list[0] if settings_list else None
        filter = {}
        query = ""
        if email_id and len(email_id) > 0:
            filter["document_id"] = {"$in": email_id}

        if subject != "":
            query += f", subject: {subject} "
        if body != "":
            query += f", body: {body} "

        if not writing_style:
            writing_style = ""
            if settings:
                writing_style = settings.email_preferences.get("writing_style")
                writing_style += (
                    "Use emojis" if settings.email_preferences.get("use_emojis") else ""
                )
                writing_style += (
                    "Always include greetings"
                    if settings.email_preferences.get("always_include_greetings")
                    else ""
                )

        return StreamingResponse(
            pinecone.suggest(
                user_id=user_id,
                query=query,
                filter=filter,
                name=user.name,
                writing_style=EMAIL_COMPOSER_PROMPTS[writing_style],
            ),
            media_type="application/json",
        )
