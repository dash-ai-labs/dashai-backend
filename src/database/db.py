from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from src.libs.const import POSTGRES_URL

# Ensure POSTGRES_URL is available
if not POSTGRES_URL:
    raise ValueError("POSTGRES_URL environment variable is not set")

# Configure engine with connection pooling and reconnection settings
engine = create_engine(
    POSTGRES_URL,
    poolclass=QueuePool,
    pool_size=6,  # Number of connections to maintain in pool
    max_overflow=10,  # Additional connections beyond pool_size
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_timeout=30,  # Timeout when getting connection from pool
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
