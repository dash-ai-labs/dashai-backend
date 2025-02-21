import uuid
from datetime import datetime

from sqlalchemy import UUID, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import Session, relationship

from src.database.db import Base


class Token(Base):
    __tablename__ = "tokens"
    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    token = Column(String, unique=True, index=True)
    refresh_token = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    email_account_id = Column(UUID, ForeignKey("email_accounts.id"))
    email_account = relationship("EmailAccount", back_populates="token")

    @classmethod
    def get_or_create_token(
        cls, db: Session, email_account_id: UUID, token: str, refresh_token: str
    ):
        token = db.query(cls).filter(cls.email_account_id == email_account_id).first()
        if not token:
            token = cls(email_account_id=email_account_id, token=token, refresh_token=refresh_token)
            db.add(token)
            db.commit()
        return token
