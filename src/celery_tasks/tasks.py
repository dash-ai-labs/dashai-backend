import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Set

from celery import shared_task
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from tqdm import tqdm

from src.database.contact import Contact
from src.base import Message
from src.base.outlook_message import OutlookMessage
from src.database import Email, EmailAccount, Token, User, get_db
from src.database.cache import cache
from src.database.email_account import EmailAccountStatus, EmailProvider
from src.database.email_attachment import EmailAttachment
from src.database.email_label import EmailLabel
from src.database.notification import Notification
from src.database.settings import Settings
from src.database.user import MembershipStatus
from src.libs.const import DISCORD_USER_ALERTS_CHANNEL
from src.libs.discord_service import send_discord_message
from src.libs.text_utils import summarize_text
from src.libs.types import EmailFolder
from src.services import GmailService
from src.services.outlook_service import OutlookService

MINUTES = 60 * 24
BACKFILL_DAYS = 3
CHUNK_SIZE = 100  # Define the size of each chunk

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

# Silence specific noisy loggers
logging.getLogger("llama_index").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)  # openai uses httpx under the hood
logging.getLogger("pinecone").setLevel(logging.ERROR)


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

                # Embed new attachments
                embed_new_attachments.delay(str(email_account.user_id))

                email_account.status = EmailAccountStatus.SUCCESS
                db.add(email_account)
                db.commit()
            except Exception as e:
                email_account.status = EmailAccountStatus.FAILED
                db.add(email_account)
                db.commit()
                print(e)


@shared_task(name="get_new_emails")
def get_new_emails(user_id: str = None):
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
            if user_id:
                all_email_accounts = (
                    db.query(EmailAccount).filter(EmailAccount.user_id == user_id).all()
                )
            else:
                all_email_accounts = db.query(EmailAccount).all()

            for email_account in all_email_accounts:
                if (
                    email_account.user.waitlisted
                    or email_account.user.membership_status != MembershipStatus.ACTIVE
                ):
                    continue
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
    if email_account.provider == EmailProvider.OUTLOOK:
        return from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        return from_date.strftime("%Y/%m/%d")


def _process_gmail_folder(
    db: Session,
    gmail_service: GmailService,
    email_account: EmailAccount,
    folder: EmailFolder,
    from_date: str,
) -> Set[str]:
    """
    Process emails for a specific Gmail folder.

    Args:
        db (Session): Database session
        gmail_service (GmailService): Gmail service instance
        email_account (EmailAccount): Email account being processed
        folder (EmailFolder): The folder to process
        from_date (str): Date string to fetch emails from

    Returns:
        Set[str]: Set of new message IDs processed
    """
    messages = gmail_service.list_messages(q=f"after:{from_date}", folder=folder)
    if len(messages) > 0:
        message_ids = [message["id"] for message in messages]

        # Check for existing messages
        existing_messages = _get_existing_messages(db, message_ids, email_account.id)

        # Identify new messages
        new_message_ids = set(message_ids) - set(existing_messages)

        # Process and insert new emails in chunks
        if len(new_message_ids) > 0:
            _insert_new_emails(db, gmail_service, email_account, new_message_ids, folder)
    else:
        return set()


def _process_outlook_folder(
    db: Session,
    outlook_service: OutlookService,
    email_account: EmailAccount,
    folder: EmailFolder,
    from_date: str,
) -> Set[str]:
    """
    Process emails for a specific Outlook folder.

    Args:
        db (Session): Database session
        outlook_service (OutlookService): Outlook service instance
        email_account (EmailAccount): Email account being processed
        folder (EmailFolder): The folder to process
        from_date (str): Date string to fetch emails from

    Returns:
        Set[str]: Set of new message IDs processed
    """
    if folder == EmailFolder.INBOX:
        messages = asyncio.run(outlook_service.list_messages(from_date))
    else:
        messages = asyncio.run(outlook_service.list_messages_for_folder(folder, from_date))

    if len(messages) > 0:
        message_ids = [message.id for message in messages]
        existing_messages = _get_existing_messages(db, message_ids, email_account.id)
        new_message_ids = set(message_ids) - set(existing_messages)
        new_messages = [message for message in messages if message.id not in existing_messages]
        if len(new_message_ids) > 0:
            _insert_new_outlook_emails(db, email_account, new_messages, folder, outlook_service)
        return new_message_ids
    else:
        logger.info(f"No new {folder.value} emails found for {email_account.id}")
        return set()


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
    if email_account.provider == EmailProvider.GMAIL:
        # Initialize Gmail service
        gmail_service = GmailService(token=token)

        # Fetch message IDs
        _process_gmail_folder(db, gmail_service, email_account, EmailFolder.INBOX, from_date)
        _process_gmail_folder(db, gmail_service, email_account, EmailFolder.SENT, from_date)
        _process_gmail_folder(db, gmail_service, email_account, EmailFolder.DRAFTS, from_date)
        _process_gmail_folder(db, gmail_service, email_account, EmailFolder.TRASH, from_date)
        _process_gmail_folder(db, gmail_service, email_account, EmailFolder.SPAM, from_date)

    elif email_account.provider == EmailProvider.OUTLOOK:
        outlook_service = OutlookService(token=token, db=db)

        # Process different email folders
        _process_outlook_folder(db, outlook_service, email_account, EmailFolder.INBOX, from_date)
        _process_outlook_folder(db, outlook_service, email_account, EmailFolder.SENT, from_date)
        _process_outlook_folder(db, outlook_service, email_account, EmailFolder.DRAFTS, from_date)

        # Process remaining folders
        _process_outlook_folder(db, outlook_service, email_account, EmailFolder.TRASH, from_date)
        _process_outlook_folder(db, outlook_service, email_account, EmailFolder.SPAM, from_date)

    _finalize_account_sync(db, email_account)


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


def _get_existing_messages(db: Session, message_ids: List[str], email_account_id: str) -> Set[str]:
    """
    Retrieve existing message IDs from the database.

    Args:
        db (Session): Database session
        message_ids (List[str]): List of message IDs to check

    Returns:
        Set[str]: Set of existing message IDs
    """
    return {
        email_id
        for email_id, in db.query(Email.email_id).filter(
            Email.email_id.in_(message_ids), Email.email_account_id == email_account_id
        )
    }


def _insert_new_emails(
    db: Session,
    gmail_service: GmailService,
    email_account: EmailAccount,
    new_message_ids: Set[str],
    folder: EmailFolder,
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
    attachments_created: List[EmailAttachment] = []
    settings: Settings = Settings.get_or_create_settings(db, email_account.id)

    for message_id in new_message_ids:
        try:
            email = gmail_service.get_message(message_id)
            message = Message(email)
            if any(
                email_address in message.get_from()
                for email_address in settings.email_list[EmailFolder.INBOX]
            ):
                email = Email(
                    email_account=email_account, message=message, folder=EmailFolder.INBOX
                )
                emails_created.append(email)
                for attachment in message.get_attachments():
                    attachment = EmailAttachment(
                        email_id=email.id,
                        attachment_id=attachment["id"],
                        name=attachment["name"],
                        content_type=attachment["content_type"],
                        size=attachment["size"],
                    )
                    attachments_created.append(attachment)
            elif any(
                email_address in message.get_from()
                for email_address in settings.email_list[EmailFolder.SPAM]
            ):
                emails_created.append(
                    Email(email_account=email_account, message=message, folder=EmailFolder.SPAM)
                )
            elif any(
                email_address in message.get_from()
                for email_address in settings.email_list[EmailFolder.TRASH]
            ):
                emails_created.append(
                    Email(email_account=email_account, message=message, folder=EmailFolder.TRASH)
                )
            else:
                email = Email(email_account=email_account, message=message, folder=folder)
                emails_created.append(email)
                if folder == EmailFolder.INBOX or folder == EmailFolder.SENT:
                    for attachment in message.get_attachments():
                        attachment = EmailAttachment(
                            email_id=email.id,
                            attachment_id=attachment["id"],
                            name=attachment["name"],
                            content_type=attachment["content_type"],
                            size=attachment["size"],
                        )
                        attachments_created.append(attachment)

            # Commit in chunks
            if len(emails_created) >= CHUNK_SIZE:
                _commit_emails(db, emails_created)
                if email_account.status != EmailAccountStatus.SUCCESS:
                    email_account.status = EmailAccountStatus.SUCCESS
                    db.add(email_account)
                    db.commit()
                emails_created = []

        except Exception as message_error:
            logger.warning(
                f"Failed to process message {message_id} for account {email_account.id}: {message_error}",
                exc_info=True,
            )

    # Commit any remaining emails
    if emails_created:
        _commit_emails(db, emails_created)


def _insert_new_outlook_emails(
    db: Session,
    email_account: EmailAccount,
    new_messages: list[OutlookMessage],
    folder: EmailFolder,
    outlook_service: OutlookService,
):
    """
    Insert new Outlook emails in chunks.

    Args:
        db (Session): Database session
        email_account (EmailAccount): Email account being processed
        new_messages (List[any]): List of new messages to process
    """
    emails_created: List[Email] = []
    attachments_created: List[EmailAttachment] = []
    settings: Settings = Settings.get_or_create_settings(db, email_account.id)
    for message in new_messages:
        try:
            message = OutlookMessage(message)
            if any(
                email_address in message.get_from()
                for email_address in settings.email_list[EmailFolder.INBOX]
            ):
                email = Email(
                    email_account=email_account, message=message, folder=EmailFolder.INBOX
                )
                emails_created.append(email)
                for attachment in asyncio.run(
                    outlook_service.get_attachments(message.get_email_id())
                ):
                    outlook_attachment = EmailAttachment(
                        email_id=email.id,
                        attachment_id=attachment["id"],
                        name=attachment["name"],
                        content_type=attachment["contentType"],
                        size=attachment["size"],
                    )
                    attachments_created.append(outlook_attachment)

            elif any(
                email_address in message.get_from()
                for email_address in settings.email_list[EmailFolder.SPAM]
            ):
                emails_created.append(
                    Email(email_account=email_account, message=message, folder=EmailFolder.SPAM)
                )
            elif any(
                email_address in message.get_from()
                for email_address in settings.email_list[EmailFolder.TRASH]
            ):
                emails_created.append(
                    Email(email_account=email_account, message=message, folder=EmailFolder.TRASH)
                )
            else:
                email = Email(email_account=email_account, message=message, folder=folder)
                emails_created.append(email)
                if folder == EmailFolder.INBOX or folder == EmailFolder.SENT:
                    for attachment in asyncio.run(
                        outlook_service.get_attachments(message.get_email_id())
                    ):
                        outlook_attachment = EmailAttachment(
                            email_id=email.id,
                            attachment_id=attachment["id"],
                            name=attachment["name"],
                            content_type=attachment["contentType"],
                            size=attachment["size"],
                        )
                        attachments_created.append(outlook_attachment)

            # Commit in chunks
            if len(emails_created) >= CHUNK_SIZE:
                _commit_emails(db, emails_created, attachments_created)
                if email_account.status != EmailAccountStatus.SUCCESS:
                    email_account.status = EmailAccountStatus.SUCCESS
                    db.add(email_account)
                    db.commit()
                emails_created = []
                attachments_created = []
        except Exception as e:
            logger.warning(
                f"Failed to process message {message.id} for account {email_account.id}: {e}",
                exc_info=True,
            )

    if emails_created:
        _commit_emails(db, emails_created, attachments_created)


def _commit_emails(db: Session, emails: List[Email], attachments: List[EmailAttachment] = None):
    """
    Commit emails to the database with error handling.

    Args:
        db (Session): Database session
        emails (List[Email]): List of emails to commit
    """
    try:
        db.add_all(emails)
        if attachments:
            db.add_all(attachments)
        db.commit()
        logger.info(f"Committed {len(emails)} new emails")
    except SQLAlchemyError as commit_error:
        db.rollback()
        logger.error(f"Failed to commit emails: {commit_error}", exc_info=True)


def _finalize_account_sync(db: Session, email_account: EmailAccount):
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
        if user_id:
            users = [db.query(User).filter(User.id == user_id).first()]
        else:
            users = db.query(User).all()
        for user in users:
            if user.membership_status == MembershipStatus.INACTIVE:
                continue
            user_id = user.id
            one_week_ago = datetime.now() - timedelta(days=7)
            emails = (
                db.query(Email)
                .filter(
                    Email.email_account.has(user_id=user_id),
                    Email.processed == False,
                    Email.folder.notin_(
                        [
                            EmailFolder.TRASH.value,
                            EmailFolder.SPAM.value,
                            EmailFolder.DRAFTS.value,
                        ]
                    ),
                    Email.created_at >= one_week_ago,
                )
                .all()
            )

            # Process emails in batches of 20
            print("Embedding emails and storing in VectorDB for user: ", user_id)
            processed_email_count = 0
            for email in emails:
                Contact.get_or_create_contact(
                    db,
                    email_account_id=email.email_account_id,
                    email_address=email.sender,
                    name=email.sender_name,
                )
                response = Email.embed_and_store(user_id=user_id, email=email)
                processed_email_count += 1
                if response:
                    email.processed = True
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


@shared_task(name="embed_new_attachments")
def embed_new_attachments(user_id: str = None):
    with get_db() as db:
        users = db.query(User).all()
        for user in users:
            user_id = user.id
            if user.membership_status == MembershipStatus.INACTIVE:
                continue
            ##### Gmail #####
            print("Embedding new attachments for Gmail for user: ", user_id)
            email_accounts = (
                db.query(EmailAccount)
                .filter(
                    EmailAccount.user_id == user_id, EmailAccount.provider == EmailProvider.GMAIL
                )
                .all()
            )
            for email_account in email_accounts:
                gmail_service = GmailService(email_account.token)
                try:
                    attachments = (
                        db.query(EmailAttachment)
                        .join(Email)
                        .filter(
                            Email.email_account_id == email_account.id,
                            EmailAttachment.processed == False,
                        )
                        .all()
                    )
                except Exception as e:
                    logger.error(
                        f"Error getting attachments for user {user_id}: {e}", exc_info=True
                    )
                    continue

                if attachments and len(attachments) > 0:
                    for attachment in attachments:
                        try:
                            attachment.embed_and_store(
                                user_id=user_id,
                                email_id=attachment.email.email_id,
                                attachment=attachment,
                                gmail_service=gmail_service,
                            )
                            attachment.processed = True
                            db.add(attachment)
                        except Exception as e:
                            logger.error(
                                f"Error embedding attachment for user {user_id}: {e}", exc_info=True
                            )
                            continue
                    db.commit()

            ##### Outlook #####
            print("Embedding new attachments for Outlook for user: ", user_id)
            email_accounts = (
                db.query(EmailAccount)
                .filter(
                    EmailAccount.user_id == user_id, EmailAccount.provider == EmailProvider.OUTLOOK
                )
                .all()
            )
            for email_account in email_accounts:
                outlook_service = OutlookService(email_account.token)
                attachments = (
                    db.query(EmailAttachment)
                    .join(Email)
                    .filter(
                        Email.email_account_id == email_account.id,
                        EmailAttachment.processed == False,
                    )
                    .all()
                )
                if attachments and len(attachments) > 0:
                    for attachment in attachments:
                        try:
                            attachment.embed_and_store(
                                user_id=user_id,
                                email_id=attachment.email.email_id,
                                attachment=attachment,
                                outlook_service=outlook_service,
                            )
                            attachment.processed = True
                            db.add(attachment)
                        except Exception as e:
                            logger.error(
                                f"Error embedding attachment for user {user_id}: {e}", exc_info=True
                            )
                            continue
                    db.commit()

            print("Finished embedding new attachments for user: ", user_id)


@shared_task(name="delete_user")
def delete_user(user_id: str):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_email = user.email

            try:
                emails = db.query(Email).filter(Email.email_account.has(user_id=user_id)).all()
                for email in emails:
                    db.delete(email)
            except Exception as e:
                logger.error(f"Error deleting emails for user {user_id}: {e}", exc_info=True)
            try:
                email_accounts = (
                    db.query(EmailAccount).filter(EmailAccount.user_id == user_id).all()
                )
                for email_account in email_accounts:
                    db.delete(email_account)
            except Exception as e:
                logger.error(
                    f"Error deleting email accounts for user {user_id}: {e}", exc_info=True
                )

            try:
                tokens = db.query(Token).filter(Token.user_id == user_id).all()
                for token in tokens:
                    db.delete(token)
            except Exception as e:
                logger.error(f"Error deleting tokens for user {user_id}: {e}", exc_info=True)
            try:
                notifications = db.query(Notification).filter(Notification.user_id == user_id).all()
                for notification in notifications:
                    db.delete(notification)
            except Exception as e:
                logger.error(f"Error deleting notifications for user {user_id}: {e}", exc_info=True)
            try:
                email_labels = db.query(EmailLabel).filter(EmailLabel.user_id == user_id).all()
                for email_label in email_labels:
                    db.delete(email_label)
            except Exception as e:
                logger.error(f"Error deleting email labels for user {user_id}: {e}", exc_info=True)

            db.delete(user)
            db.commit()
            send_discord_message(f"User {user_email} has been deleted", DISCORD_USER_ALERTS_CHANNEL)
        else:
            logger.warning(f"User with ID {user_id} not found")
