# src/database/weekly_email_recap.py
import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session, relationship

from src.database.db import Base


class WeeklyEmailRecap(Base):
    __tablename__ = "weekly_email_recaps"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    email_account_id = Column(UUID, ForeignKey("email_accounts.id"), nullable=False)
    email_account = relationship("EmailAccount", back_populates="weekly_email_recap")
    completed = Column(Boolean, default=False)
    # store all email IDs for the recap in this array
    email_ids = Column(ARRAY(UUID), default=list)

    @classmethod
    def add_to_latest_recap(cls, db: Session, email_account_id, email_ids):
        """Add emails from this week to weekly recap"""
        if latest_recap := cls.get_latest_recap(db, email_account_id):
            latest_recap.email_ids.extend(email_ids)
            db.add(latest_recap)
            db.commit()

    @classmethod
    def get_latest_recap(cls, db: Session, email_account_id):
        return (
            db.query(cls)
            .filter(cls.email_account_id == email_account_id)
            .order_by(WeeklyEmailRecap.week_start.desc())
            .first()
        )
