# src/database/weekly_email_recap.py
import uuid
from datetime import datetime, date, timedelta
from sqlalchemy import UUID, Column, DateTime, ForeignKey, String, UnicodeText
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from src.database.db import Base

class WeeklyEmailRecap(Base):
    __tablename__ = "weekly_email_recaps"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    summary = Column(UnicodeText, nullable=True)

    email_account_id = Column(UUID, ForeignKey("email_accounts.id"), nullable=False)
    email_account = relationship("EmailAccount", back_populates="weekly_email_recap")

    email_id = Column(UUID, ForeignKey("emails.id"), nullable=False)
    email = relationship("Email")
    categories = Column(ARRAY(String))

    @classmethod
    def add_to_latest_recap(cls, db, email_account_id, emails):
        """Add emails from this week to weekly recap"""

        week_start = date.today() - timedelta(days=date.today().weekday())  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday
    
        recaps = []
        for email in emails:
            recap = cls(
                week_start=week_start,
                week_end=week_end,
                summary=email.summary,
                email_account_id=email_account_id,
                email_id=email.id,
                categories=email.categories
            )
            db.add(recap)
            recaps.append(recap)
    
        db.commit()