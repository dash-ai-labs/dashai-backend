import uuid
from datetime import datetime

from sqlalchemy import UUID, Column, DateTime, String
from sqlalchemy.orm import relationship

from src.database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    google_id = Column(String, unique=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    profile_pic = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    email_accounts = relationship(
        "EmailAccount",
        back_populates="user",
    )
    email_labels = relationship("EmailLabel", back_populates="user")

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "last_login": self.last_login,
            "profile_pic": self.profile_pic,
            "email_accounts": [email_account.to_dict() for email_account in self.email_accounts],
        }
