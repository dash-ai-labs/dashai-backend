import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    Column,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Session, relationship

from src.database.db import Base


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    name = Column(String)
    email_address = Column(String)

    email_account_id = Column(UUID, ForeignKey("email_accounts.id"))
    email_account = relationship("EmailAccount", back_populates="contacts")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "email_address": self.email_address,
            "email_account_id": str(self.email_account_id),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def get_or_create_contact(
        cls, db: Session, email_account_id: str, email_address: str, name: str
    ):
        contact = (
            db.query(cls)
            .filter(cls.email_account_id == email_account_id, cls.email_address == email_address)
            .first()
        )
        if contact:
            return contact
        else:
            contact = cls(
                email_account_id=email_account_id,
                email_address=email_address,
                name=name,
            )
            db.add(contact)
            db.commit()
            return contact
