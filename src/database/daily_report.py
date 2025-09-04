from enum import Enum
import uuid
from datetime import datetime

from sqlalchemy import UUID, Column, ARRAY, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from src.database.db import Base


class DailyReportType(str, Enum):
    MORNING = "morning"
    EVENING = "evening"


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(UUID, ForeignKey("users.id"))
    user = relationship("User", back_populates="daily_reports")
    daily_report = Column(String)
    daily_report_type = Column(String)
    sent_at = Column(DateTime)
    actionable_email_ids = Column(ARRAY(String))
    information_email_ids = Column(ARRAY(String))
    text_report = Column(String)
    html_report = Column(String)
