import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timedelta

from google.cloud import storage
from llama_index.core import SimpleDirectoryReader
from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.database.db import Base
from src.database.email_account import EmailProvider
from src.database.vectory_db import VectorDB
from src.libs.const import GCP_BUCKET_CREDENTIALS, GCP_BUCKET_NAME, STAGE
from src.services.gmail_service import GmailService
from src.services.outlook_service import OutlookService

vector_db = VectorDB()

if STAGE == "production":
    storage_client = storage.Client.from_service_account_info(json.loads(GCP_BUCKET_CREDENTIALS))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


class EmailAttachment(Base):
    __tablename__ = "email_attachments"
    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    email_id = Column(UUID, ForeignKey("emails.id"))
    email = relationship("Email", back_populates="attachments")
    attachment_id = Column(String)
    name = Column(String)
    content_type = Column(String)
    size = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    processed = Column(Boolean, default=False)
    uploaded = Column(Boolean, default=False)
    filepath = Column(String)

    @property
    def url(self):
        if STAGE == "production":
            bucket = storage_client.bucket(GCP_BUCKET_NAME)
            blob = bucket.blob(self.filepath)
            url = blob.generate_signed_url(
                version="v4", expiration=timedelta(minutes=10), method="GET"
            )
        else:
            url = f"https://storage.googleapis.com/{GCP_BUCKET_NAME}/{self.id}"

        return url

    def __init__(
        self,
        email_id: str,
        attachment_id: str,
        name: str,
        content_type: str = None,
        size: int = None,
    ):
        self.email_id = email_id
        self.attachment_id = attachment_id
        self.name = name
        if content_type:
            self.content_type = content_type
        if size:
            self.size = size

    def to_dict(self):
        try:
            return {
                "name": self.name,
                "content_type": self.content_type,
                "url": self.url,
                "size": self.size,
            }
        except Exception as e:
            logger.error(f"Warning: Failed to serialize attachment {self.id}: {e}")
            return None

    def _create_document(self, filepath: str):
        documents = SimpleDirectoryReader(
            input_files=[filepath],
            file_metadata={
                "name": self.name,
                "content_type": self.content_type,
                "email_id": self.email_id,
                "attachment_id": self.attachment_id,
                "size": self.size,
                "created_at": self.created_at,
                "id": self.id,
            },
        ).load_data()
        return documents

    @staticmethod
    def embed_and_store(
        user_id: str,
        email_id: str,
        attachment: "EmailAttachment",
        gmail_service: GmailService = None,
        outlook_service: OutlookService = None,
    ):
        if attachment.processed:
            return True
        # If email has content, create a document
        if gmail_service:
            gmail_attachment = gmail_service.get_attachment(
                message_id=email_id, attachment_id=attachment.attachment_id
            )
            attachment_data = base64.urlsafe_b64decode(gmail_attachment["data"])
            filepath = f"attachments/{user_id}/{email_id}/{attachment.name}"
            attachment.size = gmail_attachment["size"]
        if outlook_service:
            outlook_attachment = asyncio.run(
                outlook_service.get_attachment(
                    message_id=email_id, attachment_id=attachment.attachment_id
                )
            )
            attachment_data = base64.urlsafe_b64decode(outlook_attachment.content_bytes)
            filepath = f"attachments/{user_id}/{email_id}/{attachment.name}"

        try:
            bucket = storage_client.bucket(GCP_BUCKET_NAME)
            blob = bucket.blob(filepath)
            blob.upload_from_string(attachment_data, content_type=attachment.content_type)
            attachment.filepath = filepath
            attachment.uploaded = True
        except Exception as e:
            print(f"Error uploading attachment: {attachment.id} to GCP: ", e)
            return False

        # try:
        #     with open(f"/temp_file_storage/{filepath}", "wb") as f:
        #         f.write(attachment_data)
        #     vector_db.insert(attachment._create_document(f"/temp_file_storage/{filepath}"), user_id)
        # except Exception as e:
        #     print(f"Error embedding attachment: {attachment.id} to VectorDB: ", e)
        #     return False

        return True
