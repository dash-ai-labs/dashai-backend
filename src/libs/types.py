from enum import Enum
from typing import List

from pydantic import BaseModel


class EmailData(BaseModel):
    from_addr: str
    to: List[str]
    cc: List[str]
    bcc: List[str]
    subject: str
    body: str
    attachments: List[str]


class EmailFolder(str, Enum):
    INBOX = "inbox"
    SENT = "sent"
    DRAFTS = "drafts"
    SPAM = "spam"
    TRASH = "trash"
