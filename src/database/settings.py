from datetime import datetime
import uuid
from enum import Enum

from sqlalchemy import JSON, UUID, Column, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Session

from src.database.db import Base
from src.libs.types import EmailFolder


class WritingStyle(str, Enum):
    CASUAL = "casual"
    LAWYER = "lawyer"
    SCIENTIST = "scientist"
    MARKETER = "marketer"
    WRITER = "writer"
    ACCOUNTANT = "accountant"
    GENZ = "genz"
    MANAGER = "manager"


class Settings(Base):
    __tablename__ = "settings"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    email_account_id = Column(UUID, ForeignKey("email_accounts.id"))
    email_account = relationship("EmailAccount", back_populates="settings")
    email_list = Column(
        JSON,
        default={
            EmailFolder.INBOX: [],
            EmailFolder.SPAM: [],
            EmailFolder.TRASH: [],
        },
    )
    email_preferences = Column(
        JSON,
        default={"use_emojis": True, "always_include_greetings": True, "writing_style": "casual"},
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "email_account_id": self.email_account_id,
            "email_list": self.email_list,
            "email_preferences": self.email_preferences,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def get_or_create_settings(cls, db: Session, email_account_id: UUID):
        settings = db.query(Settings).filter(Settings.email_account_id == email_account_id).first()
        if settings:
            return settings
        else:
            settings = Settings(email_account_id=email_account_id)
            db.add(settings)
            db.commit()
            db.refresh(settings)
            return settings
