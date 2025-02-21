from sqlalchemy import UUID, Column, ForeignKey, Table

from src.database.db import Base

email_lable_association_table = Table(
    "email_label_association",  # Table name
    Base.metadata,
    Column("email_id", UUID, ForeignKey("emails.id"), primary_key=True),
    Column("email_label_id", UUID, ForeignKey("email_labels.id"), primary_key=True),
)
