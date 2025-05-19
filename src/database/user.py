import uuid
from datetime import datetime

from sqlalchemy import JSON, UUID, Boolean, Column, DateTime, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.database.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("outlook_id", name="unique_outlook_id"),
        UniqueConstraint("google_id", name="unique_google_id"),
    )

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    google_id = Column(String, unique=True, nullable=True)
    outlook_id = Column(String, unique=True, nullable=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    profile_pic = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    email_accounts = relationship(
        "EmailAccount",
        back_populates="user",
    )
    notifications = relationship("Notification", back_populates="user")
    email_labels = relationship("EmailLabel", back_populates="user")
    waitlisted = Column(Boolean, default=True)
    referrals = Column(JSON, default=[])
    show_tutorial = Column(Boolean, default=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "last_login": self.last_login,
            "profile_pic": self.profile_pic,
            "email_accounts": [email_account.to_dict() for email_account in self.email_accounts],
            "waitlisted": self.waitlisted,
            "show_tutorial": self.show_tutorial,
        }
