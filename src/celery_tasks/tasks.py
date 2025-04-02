import logging
from datetime import datetime, timedelta
from typing import List, Set

from celery import shared_task
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from tqdm import tqdm

from src.base import Message
from src.database import Email, EmailAccount, Token, User, get_db
from src.database.email_account import EmailAccountStatus
from src.libs.text_utils import summarize_text
from src.services import GmailService

MINUTES = 60 * 24
BACKFILL_DAYS = 3
CHUNK_SIZE = 100  # Define the size of each chunk

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@shared_task(name="ingest_email")
def ingest_email(email_account_id: str):
    logger.info(f"Ingesting emails for {email_account_id}")
    with get_db() as db:
        email_account = db.query(EmailAccount).get(email_account_id)
        if email_account.status == EmailAccountStatus.NOT_STARTED:
            try:
                from_date = _calculate_sync_date(email_account)
                email_account.status = EmailAccountStatus.SYNCING
                db.add(email_account)
                db.commit()

                # Fetch and process emails
                _process_email_account(db, email_account, from_date)

                # Embed new emails
                embed_new_emails.delay(str(email_account.user_id))

                email_account.status = EmailAccountStatus.SUCCESS
                db.add(email_account)
                db.commit()
            except Exception as e:
                email_account.status = EmailAccountStatus.FAILED
                db.add(email_account)
                db.commit()
                print(e)


@shared_task(name="get_new_emails")
def get_new_emails():
    """
    Synchronize new emails for all email accounts with robust error handling and logging.

    This function:
    - Fetches emails for each email account
    - Handles token and service exceptions
    - Chunks email insertions
    - Logs detailed error information
    - Ensures minimal disruption if one account fails
    """
    try:
        with get_db() as db:
            all_email_accounts = db.query(EmailAccount).all()

            for email_account in all_email_accounts:
                try:
                    # Determine date range for email fetch
                    from_date = _calculate_sync_date(email_account)

                    # Fetch and process emails
                    _process_email_account(db, email_account, from_date)

                except Exception as account_error:
                    logger.error(
                        f"Failed to process email account {email_account.id}: {account_error}",
                        exc_info=True,
                    )
                    db.rollback()
                    # Optionally, send an alert or notification about the failed account
                    continue

    except SQLAlchemyError as db_error:
        logger.critical(f"Database connection error: {db_error}", exc_info=True)

    except Exception as unexpected_error:
        logger.critical(
            f"Unexpected error in email synchronization: {unexpected_error}",
            exc_info=True,
        )


def _calculate_sync_date(email_account: EmailAccount) -> str:
    """
    Calculate the date from which to fetch emails.

    Args:
        email_account (EmailAccount): The email account being synchronized

    Returns:
        str: Formatted date string for email fetch
    """
    if email_account.last_sync:
        # Go back one day to catch any potentially missed emails
        from_date = email_account.last_sync - timedelta(days=1)
    else:
        # For first-time sync, go back BACKFILL_DAYS
        from_date = datetime.now() - timedelta(days=BACKFILL_DAYS)

    return from_date.strftime("%Y/%m/%d")


def _process_email_account(db: Session, email_account: EmailAccount, from_date: str):
    """
    Process emails for a specific email account.

    Args:
        db (Session): Database session
        email_account (EmailAccount): Email account to process
        from_date (str): Date string to fetch emails from
    """
    # Validate and fetch token
    token = _validate_token(email_account)

    # Initialize Gmail service
    gmail_service = GmailService(token=token)

    # Fetch message IDs
    messages = gmail_service.list_messages(q=f"after:{from_date}")
    if len(messages) > 0:
        message_ids = [message["id"] for message in messages]

        # Check for existing messages
        existing_messages = _get_existing_messages(db, message_ids)

        # Identify new messages
        new_message_ids = set(message_ids) - existing_messages

        # Process and insert new emails in chunks
        _insert_new_emails(db, gmail_service, email_account, new_message_ids)

        # Update last sync time and trigger email embedding
        _finalize_account_sync(db, email_account, new_message_ids)
    else:
        logger.info(f"No new emails found for {email_account.id}")


def _validate_token(email_account: EmailAccount) -> Token:
    """
    Validate and retrieve the email account token.

    Args:
        email_account (EmailAccount): Email account to validate

    Returns:
        Token: Validated token

    Raises:
        ValueError: If token is invalid or missing
    """
    if not email_account.token:
        raise ValueError(f"No token found for account {email_account.id}")

    # Add additional token validation logic if needed
    return email_account.token


def _get_existing_messages(db: Session, message_ids: List[str]) -> Set[str]:
    """
    Retrieve existing message IDs from the database.

    Args:
        db (Session): Database session
        message_ids (List[str]): List of message IDs to check

    Returns:
        Set[str]: Set of existing message IDs
    """
    return {
        email_id for (email_id,) in db.query(Email.email_id).filter(Email.email_id.in_(message_ids))
    }


def _insert_new_emails(
    db: Session,
    gmail_service: GmailService,
    email_account: EmailAccount,
    new_message_ids: Set[str],
):
    """
    Insert new emails in chunks.

    Args:
        db (Session): Database session
        gmail_service (GmailService): Gmail service instance
        email_account (EmailAccount): Email account being processed
        new_message_ids (Set[str]): Set of new message IDs to process
    """
    emails_created: List[Email] = []

    for message_id in new_message_ids:
        try:
            email = gmail_service.get_message(message_id)
            emails_created.append(Email(email_account=email_account, message=Message(email)))

            # Commit in chunks
            if len(emails_created) >= CHUNK_SIZE:
                _commit_emails(db, emails_created)
                emails_created = []

        except Exception as message_error:
            logger.warning(
                f"Failed to process message {message_id} for account {email_account.id}: {message_error}",
                exc_info=True,
            )

    # Commit any remaining emails
    if emails_created:
        _commit_emails(db, emails_created)


def _commit_emails(db: Session, emails: List[Email]):
    """
    Commit emails to the database with error handling.

    Args:
        db (Session): Database session
        emails (List[Email]): List of emails to commit
    """
    try:
        db.add_all(emails)
        db.commit()
        logger.info(f"Committed {len(emails)} new emails")
    except SQLAlchemyError as commit_error:
        db.rollback()
        logger.error(f"Failed to commit emails: {commit_error}", exc_info=True)


def _finalize_account_sync(db: Session, email_account: EmailAccount, new_message_ids: Set[str]):
    """
    Finalize email account synchronization.

    Args:
        db (Session): Database session
        email_account (EmailAccount): Email account being processed
        new_message_ids (Set[str]): Set of new message IDs processed
    """
    try:
        # Update last sync time
        email_account.last_sync = datetime.now()
        db.commit()

    except Exception as finalize_error:
        logger.error(f"Error finalizing account sync: {finalize_error}", exc_info=True)
        db.rollback()


@shared_task(name="embed_new_emails")
def embed_new_emails(user_id: str = None):
    with get_db() as db:
        users = db.query(User).all()
        for user in users:
            user_id = user.id
            one_week_ago = datetime.now() - timedelta(days=7)
            emails = (
                db.query(Email)
                .filter(
                    Email.email_account.has(user_id=user_id),
                    Email.processed == False,
                    Email.created_at >= one_week_ago,
                )
                .all()
            )

            # Process emails in batches of 20
            print("Embedding emails and storing in VectorDB for user: ", user_id)
            embedded_emails = []
            processed_email_count = 0
            for email in emails:
                response = Email.embed_and_store(user_id=user_id, email=email)
                processed_email_count += 1
                if response:
                    embedded_emails.append(email)
                    db.add(email)
                    db.commit()

            print("Finished embedding and storing in VectorDB for user: ", user_id)

            print(f"Generating summaries for {len(emails)} emails...")
            for email in tqdm(emails, desc="Summarizing emails", unit="email"):
                if email.summary is None:
                    summary = summarize_text(
                        content=f"{email.subject} {email.content}", name=user.name
                    )
                    email.summary = summary
                    db.add(email)
            db.commit()
            print("Finished generating summaries.")
