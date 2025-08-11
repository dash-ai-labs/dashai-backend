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
    email_account = relationship("EmailAccount", back_populates="weekly_recaps")

    email_id = Column(UUID, ForeignKey("emails.id"), nullable=False)
    email = relationship("Email")
    categories = Column(ARRAY(String))

    @classmethod
    def create_recap(cls, db, email_account_id, emails, summary=None, week_start=None, week_end=None):
        """Create and store one weekly recap row per email."""
        
        # clear old emails before inserting new
        cls.clear_old_recaps_except_new_week(db, email_account_id)

        if not week_start or not week_end:
            week_start = date.today() - timedelta(days=date.today().weekday())  # Monday
            week_end = week_start + timedelta(days=6)  # Sunday
    
        recaps = []
        for email in emails:
            recap = cls(
                week_start=week_start,
                week_end=week_end,
                summary=summary,
                email_account_id=email_account_id,
                email_id=email.id,
                categories=email.categories
            )
            db.add(recap)
            recaps.append(recap)
    
        db.commit()
    
    @classmethod
    def clear_old_recaps_except_new_week(cls, db, email_account_id):
        today = date.today()
        current_week_start = today - timedelta(days=today.weekday())  # Monday this week
        
        delete_query = (
            db.query(cls)
            .filter(
                cls.email_account_id == email_account_id,
                cls.week_end < current_week_start
            )
        )

        deleted_count = delete_query.delete(synchronize_session="fetch")
        db.commit()
        return deleted_count
