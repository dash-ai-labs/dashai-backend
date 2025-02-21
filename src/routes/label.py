from enum import Enum

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from src.database import Color, EmailLabel, get_db
from src.routes.middleware import get_user_id

router = APIRouter()


class LabelType(Enum):
    EMAIL = "EMAIL"


@router.get("/user/{user_id}/labels")
async def get_labels(
    request: Request,
    user_id: str,
    label_type: LabelType = Query(default=""),
    user=Depends(get_user_id),
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            if label_type and label_type == LabelType.EMAIL:
                labels = (
                    db.query(EmailLabel)
                    .filter(EmailLabel.user_id == user_id)
                    .order_by(EmailLabel.created_at.desc())
                    .all()
                )
            else:
                labels = (
                    db.query(EmailLabel)
                    .filter(EmailLabel.user_id == user_id)
                    .order_by(EmailLabel.created_at.desc())
                    .all()
                )
            return [label.to_dict() for label in labels]

    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/user/{user_id}/label")
async def create_label(
    request: Request,
    user_id: str = "",
    name: str = Body(...),
    color: Color = Body(...),
    label_type: LabelType = Body(None),
    user=Depends(get_user_id),
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            if label_type and label_type == LabelType.EMAIL:
                label = EmailLabel(name=name, user_id=user_id, color=color)
            else:
                label = EmailLabel(name=name, user=user, color=color)
            db.add(label)
            db.commit()
            return label.to_dict()

    raise HTTPException(status_code=401, detail="Unauthorized")


@router.patch("/user/{user_id}/label/{label_id}")
async def update_label(
    request: Request,
    user_id: str,
    label_id: str,
    name: str = Body(...),
    color: Color = Body(...),
    user=Depends(get_user_id),
):
    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")

        label = (
            db.query(EmailLabel)
            .filter(EmailLabel.id == label_id, EmailLabel.user_id == user_id)
            .first()
        )
        if not label:
            raise HTTPException(status_code=404, detail="Label not found")

        label.name = name
        label.color = color
        db.add(label)
        db.commit()
        return label.to_dict()


@router.delete("/user/{user_id}/label/{label_id}")
async def delete_label(
    request: Request,
    user_id: str,
    label_id: str,
    user=Depends(get_user_id),
):
    with get_db() as db:
        if user_id != user.get("user_id"):
            raise HTTPException(status_code=401, detail="Unauthorized")

        label = (
            db.query(EmailLabel)
            .filter(EmailLabel.id == label_id, EmailLabel.user_id == user_id)
            .first()
        )
        if not label:
            raise HTTPException(status_code=404, detail="Label not found")

        db.delete(label)
        db.commit()
        return {"message": "Label deleted successfully"}
