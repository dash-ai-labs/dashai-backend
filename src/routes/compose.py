from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.database import User
from src.database.db import get_db
from src.database.vectory_db import VectorDB
from src.routes.middleware import get_user_id

router = APIRouter()
pinecone = VectorDB()


@router.post("/user/{user_id}/suggestion")
async def create_suggestion(
    user_id: str,
    email_id: Optional[list[str]] = Body(None),
    subject: Optional[str] = Body(None),
    body: Optional[str] = Body(None),
    user=Depends(get_user_id),
):
    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")
        user = db.query(User).filter(User.id == user_id).first()
        filter = {}
        query = ""
        if email_id and len(email_id) > 0:
            filter["document_id"] = {"$in": email_id}

        if subject != "":
            query += f", subject: {subject} "
        if body != "":
            query += f", body: {body} "

        return StreamingResponse(
            pinecone.suggest(user_id=user_id, query=query, filter=filter, name=user.name),
            media_type="application/json",
        )
