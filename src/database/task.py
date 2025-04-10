import uuid

from datetime import datetime
from sqlalchemy import UUID, Column, DateTime, ForeignKey, String, JSON
from enum import Enum as PyEnum
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from src.database.db import Base


class TaskStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Task(Base):
    __abstract__ = True

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    title = Column(String)
    description = Column(String)
    status = Column(String, default=TaskStatus.PENDING.value)
    due_date = Column(DateTime)


class EmailTask(Task):
    __tablename__ = "email_tasks"

    email_account_id = Column(UUID, ForeignKey("email_accounts.id"))
    email_account = relationship("EmailAccount", back_populates="tasks")
    email_id = Column(UUID, ForeignKey("emails.id"))
    email = relationship("Email", back_populates="tasks")
    url = Column(String)
    url_text = Column(String)
    thumbnail_url = Column(String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "due_date": self.due_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "email_account_id": self.email_account_id,
            "email_id": self.email_id,
            "url": self.url,
            "url_text": self.url_text,
            "thumbnail_url": self.thumbnail_url,
        }
