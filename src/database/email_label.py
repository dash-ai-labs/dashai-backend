from sqlalchemy import UUID, Column, ForeignKey
from sqlalchemy.orm import relationship

from src.database.association_table import email_lable_association_table
from src.database.label import Label


class EmailLabel(Label):
    __tablename__ = "email_labels"

    user_id = Column(UUID, ForeignKey("users.id"))
    user = relationship("User", back_populates="email_labels")

    emails = relationship(
        "Email", secondary=email_lable_association_table, back_populates="email_labels"
    )
