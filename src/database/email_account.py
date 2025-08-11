import base64
import uuid
from datetime import datetime
from email.message import EmailMessage
from enum import Enum as PyEnum

from fastapi import HTTPException
from sqlalchemy import UUID, Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, relationship

from src.database.db import Base
from src.database.settings import Settings
from src.libs.types import EmailData
from src.services.gmail_service import GmailService
from src.services.outlook_service import OutlookService


class EmailAccountStatus(str, PyEnum):
    NOT_STARTED = "NOT_STARTED"
    SYNCING = "SYNCING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class EmailProvider(str, PyEnum):
    GMAIL = "GMAIL"
    OUTLOOK = "OUTLOOK"


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    provider = Column(Enum(EmailProvider, name="emailprovider"))
    created_at = Column(DateTime, default=datetime.utcnow)
    profile_pic = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_sync = Column(DateTime)
    user_id = Column(UUID, ForeignKey("users.id"))
    token = relationship("Token", back_populates="email_account", uselist=False)
    user = relationship("User", back_populates="email_accounts")
    emails = relationship("Email", back_populates="email_account")
    tasks = relationship("EmailTask", back_populates="email_account")
    settings = relationship("Settings", back_populates="email_account", uselist=False)
    contacts = relationship("Contact", back_populates="email_account")
    weekly_email_recaps = relationship("WeeklyEmailRecap", back_populates="email_account")

    status = Column(
        Enum(EmailAccountStatus, name="emailaccountstatus"),
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

    async def send_email(self, email: EmailData, db: Session):
        if self.provider == EmailProvider.GMAIL:
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
        elif self.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.token, db)
            await outlook_service.send_email(email)
            return True
        else:
            raise HTTPException(status_code=400, detail="Invalid email provider")

    @classmethod
    def get_or_create_email_account(cls, db: Session, provider: EmailProvider, user, email):
        email_account = (
            db.query(cls)
            .filter(
                cls.email == email,
                cls.user_id == user.id,
                cls.provider == provider,
            )
            .first()
        )

        if email_account:
            return email_account

        email_account = cls(
            email=email,
            user_id=user.id,
            provider=provider,
        )
        settings = Settings(email_account_id=email_account.id)
        db.add(email_account)
        db.add(settings)

        try:
            db.commit()
            db.refresh(email_account)
        except IntegrityError:
            db.rollback()
            return (
                db.query(cls)
                .filter(
                    cls.email == email,
                    cls.user_id == user.id,
                    cls.provider == provider,
                )
                .first()
            )

        return email_account
