import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import UUID, Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import relationship

from src.database.db import Base


class NotificationStatus(str, PyEnum):
    UNREAD = "UNREAD"
    READ = "READ"
    ARCHIVED = "ARCHIVED"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"))
    user = relationship("User", back_populates="notifications")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    status = Column(
        Enum(NotificationStatus, name="notificationstatus"), default=NotificationStatus.UNREAD
    )
    title = Column(String)
    message = Column(String)
    link = Column(String)
    read_at = Column(DateTime)
    archived_at = Column(DateTime)

    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "message": self.message,
            "link": self.link,
            "status": self.status,
            "created_at": self.created_at,
        }
