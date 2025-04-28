from fastapi import APIRouter, Depends, HTTPException

from src.database import get_db
from src.database.notification import Notification, NotificationStatus
from src.routes.middleware import get_user_id

router = APIRouter()


@router.get("/user/{user_id}/notifications")
async def get_notifications(user_id: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        with get_db() as db:
            notifications = db.query(Notification).filter(Notification.user_id == user_id).all()
            return [notification.to_dict() for notification in notifications]
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/user/{user_id}/notification/{notification_id}/{action}")
async def update_notification(
    user_id: str, notification_id: str, action: NotificationStatus, user=Depends(get_user_id)
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            notification = (
                db.query(Notification)
                .filter(Notification.id == notification_id, Notification.user_id == user_id)
                .first()
            )
            if notification:
                notification.status = action
                db.commit()
                return notification.to_dict()
            raise HTTPException(status_code=404, detail="Notification not found")
    raise HTTPException(status_code=401, detail="Unauthorized")
