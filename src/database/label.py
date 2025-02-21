import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import UUID, Column, DateTime, String
from sqlalchemy.orm import class_mapper

from src.database.db import Base


class Color(str, PyEnum):
    GREEN = "#7CE38B"
    BLUE = "#77BDFB"
    PURPLE = "#CEA5FB"
    ORANGE = "#FAA356"
    PINK = "#FBB1AC"
    LIGHT_BLUE = "#A2D2FB"


class Label(Base):
    __abstract__ = True

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    color = Column(String, default=Color.ORANGE.value)

    def to_dict(
        self,
        allowed_columns=[
            "id",
            "name",
            "color",
        ],
    ):

        # Filter columns based on the allowed_columns list
        serialized_data = {
            column.key: getattr(self, column.key)
            for column in class_mapper(self.__class__).columns
            if column.key in allowed_columns
        }
        return serialized_data
