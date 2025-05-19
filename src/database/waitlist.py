import uuid
from datetime import datetime

from sqlalchemy import JSON, UUID, Boolean, Column, DateTime, String, UniqueConstraint

from src.database.db import Base


class OffWaitlist(Base):
    __tablename__ = "off_waitlist"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "created_at": self.created_at,
        }
