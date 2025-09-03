from datetime import datetime

from llama_index.core import Document
from pydantic import BaseModel

from src.database.email import Email
from src.database.vectory_db import VectorDB
from src.libs.rag_utils import clean_up_text

vector_db = VectorDB()

CHUNK_SIZE = 50


class EmailVector(BaseModel):
    vectors: list[float]
    metadata: dict

    class Config:
        arbitrary_types_allowed = True
        allow_population_by_field_name = True

    @classmethod
    def create(cls, user_id: str, email: Email):

        # Check if email has already been processed
        if email.processed:
            return

        # If email has content, create a document
        if email.content:
            document = cls._create_document(email)
            inserted_record = vector_db.insert([document], user_id)

            # Mark email as processed
            email.processed = True
            email.updated_at = datetime.utcnow()

            return cls(vectors=inserted_record["vectors"], metadata=inserted_record["metadata"])

    @classmethod
    def _create_document(cls, email: Email):
        cleaned_content = clean_up_text(email.content.strip())
        document = Document(
            doc_id=email.email_id,
            text=cleaned_content,
            metadata={
                "thread": email.thread_id,
                "sender": " ".join(email.sender) if email.sender else "",
                "to": " ".join(email.to),
                "cc": " ".join(email.cc),
                "subject": email.subject if email.subject else "",
                "date": email.date.strftime("%Y %m %d %B") if email.date else "",
                "id": email.email_id,
                "user": email.email_account.user.id,
            },
            excluded_embed_metadata_keys=[],
            excluded_llm_metadata_keys=[],
            relationships={},
            text_template="{metadata_str}\n\n{content}",
            metadata_template="{key}: {value}",
            metadata_seperator="\n",
        )

        return document

    @classmethod
    def create_many(cls, user_id: str, email_list: list[Email]):
        num_chunks = 0
        # Check if email list needs to be chunked
        inserted_vectors = []
        if len(email_list) > CHUNK_SIZE:

            num_chunks = len(email_list) // CHUNK_SIZE

            for i in range(num_chunks):
                start = i * CHUNK_SIZE
                end = start + CHUNK_SIZE
                chunk = email_list[start:end]
                inserted_vectors.extend(cls._embed_and_store_emails(user_id, chunk))

        remaining_email_list = email_list[num_chunks * CHUNK_SIZE :]
        if remaining_email_list:
            inserted_vectors.extend(cls._embed_and_store_emails(user_id, remaining_email_list))
        return [
            cls(vectors=inserted_vector["vectors"], metadata=inserted_vector["metadata"])
            for inserted_vector in inserted_vectors
        ]

    @classmethod
    def _embed_and_store_emails(cls, user_id, chunk: list[Email]):
        document_list = []
        for email in chunk:
            try:
                if email.processed:
                    continue
                    # If email has content, create a document
                if email.content:
                    document = cls._create_document(email)
                    document_list.append(document)
            except Exception as e:
                print(e)
                continue
        try:
            vector_db.insert(document_list, user_id)
            # Mark email as processed
        except Exception as e:
            print(
                "Error embedding emails with ids: {}".format([email.id for email in chunk]),
                e,
            )
        try:
            for email in chunk:
                email.processed = True
        except Exception as e:
            print(
                "Error updating emails with ids: {}".format([email.id for email in chunk]),
                e,
            )
