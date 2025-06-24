import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import ARRAY, JSON, UUID, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from src.database.db import Base


class Action(Enum):
    RESPOND_TO_EMAIL = "RESPOND_TO_EMAIL"
    MARK_AS_READ = "MARK_AS_READ"
    MARK_AS_UNREAD = "MARK_AS_UNREAD"


class FollowUpTask:
    email_id: str
    email_subject: str
    email_body: str
    action: Action

    def __init__(
        self, email_id: str, action: Action, email_body: str = None, email_subject: str = None
    ):
        self.email_id = email_id
        self.action = action
        self.email_body = email_body
        self.email_subject = email_subject

    def to_dict(self):
        return {
            "email_id": self.email_id,
            "action": self.action.value,
            "email_body": self.email_body,
            "email_subject": self.email_subject,
        }


class CallSession(Base):
    __tablename__ = "call_sessions"
    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user_id = Column(UUID, ForeignKey("users.id"))
    user = relationship("User", back_populates="call_sessions")
    follow_up_tasks = Column(
        ARRAY(JSON),
        default=[],
    )
    call_control_id = Column(String)
    recording_url = Column(String)
    is_completed = Column(Boolean, default=False)
    is_processed = Column(Boolean, default=False)
