from typing import Dict, List
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from src.database.db import get_db
from src.database.settings import Settings
from src.libs.types import EmailFolder
from src.routes.middleware import get_user_id

router = APIRouter()


class SettingsInput(BaseModel):
    email_list: Dict[EmailFolder, List[str]]
    email_preferences: Dict[str, bool | str]


@router.post("/user/{user_id}/email_account/{email_account_id}/settings")
async def update_settings(
    user_id: str,
    email_account_id: str,
    settings_input: SettingsInput = Body(...),
    user=Depends(get_user_id),
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            settings = (
                db.query(Settings).filter(Settings.email_account_id == email_account_id).first()
            )
            if settings:
                settings.email_list = settings_input.email_list
                settings.email_preferences = settings_input.email_preferences
                db.commit()
                return settings.to_dict()
            else:
                raise HTTPException(status_code=404, detail="Settings not found")
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/user/{user_id}/email_account/{email_account_id}/settings")
async def get_settings(user_id: str, email_account_id: str, user=Depends(get_user_id)):
    print(user_id, email_account_id)
    if user_id == user.get("user_id"):
        with get_db() as db:
            settings = Settings.get_or_create_settings(db, email_account_id)
            return settings.to_dict()
    raise HTTPException(status_code=401, detail="Unauthorized")
