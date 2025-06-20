import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import ARRAY, JSON, UUID, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from src.database.db import Base


class Action(Enum):
    SEND_EMAIL = "SEND_EMAIL"
    RESPOND_TO_EMAIL = "RESPOND_TO_EMAIL"


class FollowUpTask:
    email_id: str
    email_subject: str
    action: Action


class CallSession(Base):
    __tablename__ = "call_sessions"
    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user_id = Column(UUID, ForeignKey("users.id"))
    user = relationship("User", back_populates="call_sessions")
    follow_up_tasks = Column(ARRAY(JSON), default=[])
    call_control_id = Column(String)
    recording_url = Column(String)
    is_completed = Column(Boolean, default=False)
