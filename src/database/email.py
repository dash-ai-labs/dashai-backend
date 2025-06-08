import uuid
from datetime import datetime

from bs4 import BeautifulSoup
from fastapi import Request
from fastapi.responses import HTMLResponse
from llama_index.core import Document
from sqlalchemy import (
    UUID,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    UnicodeText,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session, class_mapper, relationship

from src.base import Message
from src.base.outlook_message import OutlookMessage
from src.database.association_table import email_lable_association_table
from src.database.db import Base
from src.database.email_account import EmailAccount, EmailProvider
from src.database.vectory_db import VectorDB
from src.libs.rag_utils import clean_up_text
from src.libs.types import EmailFolder
from src.services.gmail_service import GmailService
from src.services.outlook_service import OutlookService

pinecone = VectorDB()

CHUNK_SIZE = 50


class Email(Base):
    __tablename__ = "emails"
    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    sender = Column(ARRAY(String))
    sender_name = Column(ARRAY(String))
    to = Column(ARRAY(String))
    subject = Column(String)
    date = Column(DateTime)
    cc = Column(ARRAY(String))
    processed = Column(Boolean, default=False)
    summary = Column(String, nullable=True)
    content = Column(String, nullable=True)
    snippet = Column(String, nullable=True)
    raw_content = Column(UnicodeText, nullable=True)
    thread_id = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    labels = Column(ARRAY(String))
    folder = Column(String, default=EmailFolder.INBOX.value, server_default=EmailFolder.INBOX.value)
    email_id = Column(String)
    email_account_id = Column(UUID, ForeignKey("email_accounts.id"))
    email_account = relationship("EmailAccount", back_populates="emails")
    tasks = relationship("EmailTask", back_populates="email")
    email_labels = relationship(
        "EmailLabel", secondary=email_lable_association_table, back_populates="emails"
    )
    attachments = relationship("EmailAttachment", back_populates="email")
    __table_args__ = (
        UniqueConstraint("email_account_id", "email_id", name="unique_email_account_id_email_id"),
    )

    def __init__(
        self,
        email_account: EmailAccount,
        message: Message | OutlookMessage,
        folder: EmailFolder = EmailFolder.INBOX,
    ):
        if isinstance(message, Message):
            self.sender = message.get_from()
            self.sender_name = message.get_from_name()
            self.to = message.get_to()
            self.cc = message.get_cc()
            self.labels = message.get_label_ids()
            self.subject = message.get_subject()
            self.date = message.get_date()
            self.content = message.get_content()
            self.email_id = message.get_email_id()
            self.snippet = message.get_snippet()
            self.raw_content = message.get_raw_content()
            self.thread_id = message.get_thread_id()
            self.email_account_id = email_account.id
            self.folder = folder.value
            self.id = uuid.uuid4()
        elif isinstance(message, OutlookMessage):
            self.sender = message.get_from()
            self.sender_name = message.get_from_name()
            self.to = message.get_to()
            self.cc = message.get_cc()
            self.subject = message.get_subject()
            self.date = message.get_date()
            self.content = message.get_content()
            self.email_id = message.get_email_id()
            self.raw_content = message.get_raw_content()
            self.email_account_id = email_account.id
            self.folder = folder.value
            self.id = uuid.uuid4()

        return self

    def to_dict(
        self,
        allowed_columns=[
            "id",
            "sender",
            "sender_name",
            "to",
            "subject",
            "date",
            "cc",
            "summary",
            "snippet",
            "labels",
            "email_id",
            "email_labels",
            "is_read",
            "folder",
            "email_account_id",
            "attachments",
        ],
    ):

        # Filter columns based on the allowed_columns list
        serialized_data = {
            column.key: getattr(self, column.key)
            for column in class_mapper(self.__class__).columns
            if column.key in allowed_columns
        }
        if "email_labels" in allowed_columns:
            serialized_data["email_labels"] = [label.to_dict() for label in self.email_labels]

        serialized_data["content"] = (
            f"/user/{self.email_account.user.id}/email/{self.email_id}/content"
        )
        return serialized_data

    def sanitized_content(self, request: Request):
        nonce = request.headers.get("X-Content-Security-Policy-Nonce")

        # Return empty content if raw_content is None
        if self.raw_content is None:
            return HTMLResponse(content="")

        # Parse HTML
        soup = BeautifulSoup(self.raw_content, "html.parser")

        # Replace external stylesheets with proxied versions
        for link in soup.find_all("link", {"rel": "stylesheet"}):
            original_url = link.get("href")
            if original_url:
                proxied_url = f"/proxy-stylesheet/?url={original_url}"
                link["href"] = proxied_url

        # Apply nonce to <style> tags
        new_style_tag = soup.new_tag("style")
        new_style_tag["nonce"] = nonce
        inline_styles = []

        # Collect and process all inline styles
        for element in soup.find_all(lambda tag: tag.get("style")):
            style_content = element.get("style", "").strip()
            if style_content:
                # Generate a unique class name based on the style content
                class_name = f"inline-style-{abs(hash(style_content))}"
                existing_classes = element.get("class", [])
                if class_name not in existing_classes:
                    element["class"] = existing_classes + [class_name]
                inline_styles.append(f".{class_name} {{ {style_content} }}")
                del element["style"]

        # Add collected inline styles to the new <style> tag
        if inline_styles:
            new_style_tag.string = f"/*! nonce-{nonce} */\n" + "\n".join(inline_styles)

        # Add nonce to all existing <style> tags
        for style_tag in soup.find_all("style"):
            style_tag["nonce"] = nonce
            if style_tag.string:
                style_tag.string = f"/*! nonce-{nonce} */\n" + style_tag.string.strip()

        # Insert the new style tag into the <head> section
        if inline_styles:
            if not soup.html:
                soup.append(soup.new_tag("html"))
            if not soup.html.head:
                soup.html.append(soup.new_tag("head"))
            soup.html.head.append(new_style_tag)

        # Ensure nonce is applied consistently in <style> tags and inline styles are moved
        sanitized_html = soup.prettify()
        return sanitized_html

    async def sync_from_web(self, db: Session):
        if self.email_account.provider == EmailProvider.GMAIL:
            gmail_service = GmailService(self.email_account.token)
            full_message = gmail_service.get_message(message_id=self.email_id)
            message = Message(full_message)
            self.sender = message.get_from()
            self.sender_name = message.get_from_name()
            self.to = message.get_to()
            self.cc = message.get_cc()
            self.labels = message.get_label_ids()
            self.subject = message.get_subject()
            self.date = message.get_date()
            self.content = message.get_content()
            self.email_id = message.get_email_id()
            self.snippet = message.get_snippet()
            self.raw_content = message.get_raw_content()
            self.thread_id = message.get_thread_id()
            self.is_read = message.get_is_read()
        elif self.email_account.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.email_account.token, db)
            full_message = await outlook_service.get_message(message_id=self.email_id)
            message = OutlookMessage(full_message)
            self.sender = message.get_from()
            self.sender_name = message.get_from_name()
            self.to = message.get_to()
            self.cc = message.get_cc()
            self.labels = message.get_label_ids()
            self.subject = message.get_subject()
            self.date = message.get_date()
            self.content = message.get_content()
            self.raw_content = message.get_raw_content()
            self.is_read = message.get_is_read()
        db.add(self)
        db.commit()
        return self

    async def mark_as_read(self, db: Session):
        if self.email_account.provider == EmailProvider.GMAIL:
            gmail_service = GmailService(self.email_account.token)
            gmail_service.modify_labels(message_id=self.email_id, remove_labels=["UNREAD"])
        if self.email_account.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.email_account.token, db)
            await outlook_service.mark_as_read(self.email_id)
        self.is_read = True
        db.commit()
        return self

    async def mark_as_unread(self, db: Session):
        if self.email_account.provider == EmailProvider.GMAIL:
            gmail_service = GmailService(self.email_account.token)
            gmail_service.modify_labels(message_id=self.email_id, add_labels=["UNREAD"])
        if self.email_account.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.email_account.token, db)
            await outlook_service.mark_as_unread(self.email_id)
        self.is_read = False
        db.commit()
        return self

    async def archive(self, db: Session):

        if self.email_account.provider == EmailProvider.GMAIL:
            gmail_service = GmailService(self.email_account.token)
            gmail_service.modify_labels(message_id=self.email_id, remove_labels=["INBOX"])
            return self
        if self.email_account.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.email_account.token, db)
            await outlook_service.archive(self.email_id)
            return self

    async def delete(self, db: Session):
        self.folder = EmailFolder.TRASH.value
        db.commit()
        if self.email_account.provider == EmailProvider.GMAIL:
            gmail_service = GmailService(self.email_account.token)
            gmail_service.modify_labels(message_id=self.email_id, add_labels=["TRASH"])
            return self
        if self.email_account.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.email_account.token, db)
            await outlook_service.delete(self.email_id)
            return self

    async def move_to_inbox(self, db: Session):
        self.folder = EmailFolder.INBOX.value
        db.commit()
        if self.email_account.provider == EmailProvider.GMAIL:
            gmail_service = GmailService(self.email_account.token)
            gmail_service.modify_labels(message_id=self.email_id, add_labels=["INBOX"])
            return self
        if self.email_account.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.email_account.token, db)
            await outlook_service.move_to_inbox(self.email_id)
            return self

    async def move_to_spam(self, db: Session):
        self.folder = EmailFolder.SPAM.value
        db.commit()
        if self.email_account.provider == EmailProvider.GMAIL:
            gmail_service = GmailService(self.email_account.token)
            gmail_service.modify_labels(message_id=self.email_id, add_labels=["SPAM"])
            return self
        if self.email_account.provider == EmailProvider.OUTLOOK:
            outlook_service = OutlookService(self.email_account.token, db)
            await outlook_service.move_to_spam(self.email_id)
            return self

    def chunk_text_stream(self, text, max_chunk_length=4000, overlap=100):
        """Stream text chunks one by one."""
        start = 0
        text_length = len(text)

        # Return empty if text is empty
        if text_length == 0:
            return

        while start < text_length:
            end = min(start + max_chunk_length, text_length)

            # Break if we're not making progress
            if end <= start:
                break

            # If this is the last chunk, return it and stop
            if end == text_length:
                yield text[start:end]
                break

            yield text[start:end]

            # Ensure we advance by at least 1 character
            new_start = end - overlap
            start = max(new_start, start + 1)

    def _create_document(self):
        cleaned_content = clean_up_text((self.subject or "").strip() + (self.content or "").strip())
        # Split content into chunks if too long (assuming max tokens ~4000)
        documents = []
        for chunk in self.chunk_text_stream(cleaned_content):
            # Create a document for each chunk
            document = Document(
                doc_id=self.email_id,
                text=chunk,
                metadata={
                    "thread": self.thread_id if self.thread_id else "",
                    "sender": " ".join(self.sender) if self.sender else "",
                    "to": " ".join(self.to),
                    "cc": " ".join(self.cc),
                    "subject": self.subject if self.subject else "",
                    "date": self.date.strftime("%Y %m %d %B") if self.date else "",
                    "id": self.email_id,
                    "user": str(self.email_account.user.id),
                },
                excluded_embed_metadata_keys=[],
                excluded_llm_metadata_keys=[],
                relationships={},
                text_template="{metadata_str}\n\n{content}",
                metadata_template="{key}: {value}",
                metadata_seperator="\n",
            )
            documents.append(document)
        return documents

    @staticmethod
    def embed_and_store(user_id: str, email: "Email"):
        try:
            if email.processed:
                return True
            if email.content:
                pinecone.insert(email._create_document(), user_id)
                email.processed = True
                return True

        except Exception as e:
            print(e)
            return False
