import base64
import uuid
from datetime import datetime
from email.message import EmailMessage
from enum import Enum as PyEnum
from typing import List

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import UUID, Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, relationship

from src.database.db import Base
from src.services.gmail_service import GmailService


class EmailData(BaseModel):
    from_addr: str
    to: List[str]
    cc: List[str]
    bcc: List[str]
    subject: str
    body: str
    attachments: List[str]


class EmailAccountStatus(str, PyEnum):
    NOT_STARTED = "NOT_STARTED"
    SYNCING = "SYNCING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class EmailProvider(str, PyEnum):
    GMAIL = "GMAIL"


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    provider = Column(Enum(EmailProvider), default=EmailProvider.GMAIL)
    created_at = Column(DateTime, default=datetime.utcnow)
    profile_pic = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_sync = Column(DateTime)
    user_id = Column(UUID, ForeignKey("users.id"))
    token = relationship("Token", back_populates="email_account", uselist=False)
    user = relationship("User", back_populates="email_accounts")
    emails = relationship("Email", back_populates="email_account")
    status = Column(
        Enum(EmailAccountStatus),
        default=EmailAccountStatus.NOT_STARTED,
        server_default=EmailAccountStatus.SUCCESS,
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "provider": self.provider,
            "status": self.status,
            "created_at": self.created_at,
        }

    def send_email(self, email: EmailData):
        gmail_service = GmailService(self.token)
        message = EmailMessage()
        message["From"] = email.from_addr
        message["To"] = email.to
        message["Subject"] = email.subject
        message["Cc"] = email.cc
        message["Bcc"] = email.bcc
        message.add_header("Content-Type", "text/html")
        message.set_payload(email.body)

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}
        try:
            gmail_service.send_message(create_message)
            return True
        except Exception as e:
            print(e)
            raise HTTPException(status_code=500, detail="Failed to send email")

    @classmethod
    def get_or_create_email_account(cls, db: Session, provider: EmailProvider, user, user_info):
        email_account = (
            db.query(cls)
            .filter(
                cls.email == user_info["email"],
                cls.user_id == user.id,
                cls.provider == provider,
            )
            .first()
        )

        if email_account:
            return email_account

        email_account = cls(
            email=user_info["email"],
            user_id=user.id,
            provider=provider,
        )
        db.add(email_account)

        try:
            db.commit()
            db.refresh(email_account)
        except IntegrityError:
            db.rollback()
            return (
                db.query(cls)
                .filter(
                    cls.email == user_info["email"],
                    cls.user_id == user.id,
                    cls.provider == provider,
                )
                .first()
            )

        return email_account
