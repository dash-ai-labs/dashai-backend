import datetime
import logging
import os
from typing import List, Tuple, Optional
from enum import Enum
from celery import shared_task
from llama_index.core.output_parsers import PydanticOutputParser

from openai import BaseModel
from sqlalchemy import select

from src.libs.types import EmailFolder
from src.libs.llm_utils import create_daily_report
from src.database.email_account import EmailAccount
from src.database.email import Email
from src.libs.email_service import send_email
from src.database.daily_report import DailyReport, DailyReportType
from src.database.user import MembershipStatus, User
from src.database.db import get_db
from src.database.vectory_db import VectorDB

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

vector_db = VectorDB()


# Constants
class EmailCategory(str, Enum):
    ACTIONABLE = "actionable"
    INFORMATION = "information"


REPORT_HOURS_THRESHOLD = 12


class DailyReportResult(BaseModel):
    id: str
    summary: str
    category: str


class DailyReportResults(BaseModel):
    results: List[DailyReportResult]


parser = PydanticOutputParser(output_cls=DailyReportResults)


def serialize_email(email: Email):
    return f"""id: {str(email.id)} \
        content: {email.content}           \
        sender: {email.sender} \
        sender_name: {email.sender_name} \
        subject: {email.subject} \
        date: {email.date.strftime("%Y-%m-%d %H:%M:%S")} \
        raw_content: {email.raw_content}
    """


def load_html_template(template_name):
    """Load the HTML template for daily reports."""
    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", template_name)
    with open(template_path, "r", encoding="utf-8") as file:
        return file.read()


def generate_email_list_html(results, item_class):
    """Generate HTML list items for emails."""
    if not results or len(results) == 0:
        return '<div class="no-emails">No emails found.</div>'

    html_items = []
    for result in results:
        html_items.append(f'<div class="email-item {item_class}">{result.summary}</div>')
    return "\n".join(html_items)


def _calculate_date_threshold(db, user_id: str) -> datetime.datetime:
    """Calculate the appropriate date threshold for email filtering."""
    base_threshold = datetime.datetime.now() - datetime.timedelta(hours=REPORT_HOURS_THRESHOLD)

    earlier_report = (
        select(DailyReport)
        .where(
            DailyReport.user_id == user_id,
            DailyReport.daily_report_type == DailyReportType.MORNING.value,
            DailyReport.created_at >= base_threshold,
        )
        .limit(1)
    )
    earlier_report = db.execute(earlier_report).scalar_one_or_none()

    if earlier_report:
        # Use the earlier report's sent_at time if it exists, otherwise use created_at
        threshold = earlier_report.sent_at or earlier_report.created_at
        logger.info(f"Using previous report threshold: {threshold} for user {user_id}")
        return threshold

    logger.info(f"Using base threshold: {base_threshold} for user {user_id}")
    return base_threshold


def _get_user_email_account_ids(db, user_id: str) -> List[str]:
    """Get all email account IDs for a user."""
    return [
        email_account.id
        for email_account in db.query(EmailAccount).filter(EmailAccount.user_id == user_id)
    ]


def _query_emails_by_category(
    db, email_account_ids: List[str], category: EmailCategory, date_threshold: datetime.datetime
) -> List[Email]:
    """Query emails by category with common filters."""
    res = (
        db.query(Email)
        .filter(
            Email.email_account_id.in_(email_account_ids),
            Email.folder == EmailFolder.INBOX,
            Email.date >= date_threshold,
        )
        .order_by(Email.date.desc())
        .all()
    )
    matching_emails = []
    for email in res:
        if email.categories and category.value in email.categories:
            matching_emails.append(email)
    return matching_emails


def _generate_text_report(
    user_name: str, actionable_results: List, informational_results: List
) -> str:
    """Generate the text version of the daily report."""
    text_report = f"Hi {user_name}, your morning email report is ready.\n\n"

    # Actionable emails section
    text_report += "Actionable Emails:\n"
    if actionable_results:
        for result in actionable_results:
            text_report += f"\n* {result.summary}"
    else:
        text_report += "\n* No actionable emails found"

    # Informational emails section
    text_report += "\n\nInformational Emails:\n"
    if informational_results:
        for result in informational_results:
            text_report += f"\n* {result.summary}"
    else:
        text_report += "\n* No informational emails found"

    text_report += f"\n\nReport generated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nReport by DashAI"
    return text_report


def _generate_html_report(
    user_name: str, actionable_results: List, informational_results: List
) -> str:
    """Generate the HTML version of the daily report."""
    html_template = load_html_template("morning_report.html")
    actionable_emails_html = generate_email_list_html(actionable_results, "actionable-item")
    informational_emails_html = generate_email_list_html(
        informational_results, "informational-item"
    )

    return html_template.format(
        user_name=user_name,
        actionable_emails_content=actionable_emails_html,
        informational_emails_content=informational_emails_html,
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _process_user_emails(
    db, user: User, date_threshold: datetime.datetime, email_account_ids: List[str]
) -> Tuple[List, List]:
    """Process both actionable and informational emails for a user."""
    # Query actionable emails
    actionable_emails = _query_emails_by_category(
        db, email_account_ids, EmailCategory.ACTIONABLE, date_threshold
    )
    logger.info(f"Found {len(actionable_emails)} actionable emails for user {user.id}")

    # Query informational emails
    informational_emails = _query_emails_by_category(
        db, email_account_ids, EmailCategory.INFORMATION, date_threshold
    )
    logger.info(f"Found {len(informational_emails)} informational emails for user {user.id}")

    return actionable_emails, informational_emails


def _generate_daily_report_for_user(db, user: User) -> None:
    """Generate and send daily morning report for a single user."""
    logger.info(f"Generating daily morning report for user {user.id} ({user.email})")

    # Calculate date threshold
    date_threshold = _calculate_date_threshold(db, user.id)

    # Get user's email accounts
    email_account_ids = _get_user_email_account_ids(db, user.id)
    if not email_account_ids:
        logger.warning(f"No email accounts found for user {user.id}")
        return

    # Create daily report record
    daily_report = DailyReport(
        user_id=user.id,
        daily_report_type=DailyReportType.MORNING,
        actionable_email_ids=[],
        information_email_ids=[],
    )
    db.add(daily_report)
    db.flush()  # Get the ID without committing

    # Process emails
    actionable_emails, informational_emails = _process_user_emails(
        db, user, date_threshold, email_account_ids
    )
    # Generate reports for actionable emails
    actionable_response = None
    if actionable_emails:
        actionable_response, _ = create_daily_report(
            "\n".join([serialize_email(email) for email in actionable_emails])
        )

    # Generate reports for informational emails
    informational_response = None
    if informational_emails:
        informational_response, _ = create_daily_report(
            "\n".join([serialize_email(email) for email in informational_emails])
        )

    # Process results
    actionable_results = actionable_response.results if actionable_response.results else []
    informational_results = informational_response.results if informational_response.results else []

    # Generate reports
    text_report = _generate_text_report(user.name, actionable_results, informational_results)
    html_report = _generate_html_report(user.name, actionable_results, informational_results)

    # Update daily report
    daily_report.text_report = text_report
    daily_report.html_report = html_report

    daily_report.actionable_email_ids = [result.id for result in actionable_results]
    daily_report.information_email_ids = [result.id for result in informational_results]
    db.commit()

    # Send email
    response = send_email(user.email, "Daily Morning Report", text_report, html_report)
    if response:
        daily_report.sent_at = datetime.datetime.now()
        db.commit()
        logger.info(f"Successfully sent daily morning report to user {user.id}")
    else:
        logger.error(f"Failed to send daily morning report to user {user.id}")


@shared_task(name="daily_morning_report")
def daily_morning_report():
    """Generate and send daily morning reports for all eligible users."""
    # First, get the list of eligible users
    with get_db() as db:
        eligible_users = (
            db.query(User)
            .filter(User.membership_status.in_([MembershipStatus.ACTIVE, MembershipStatus.TRIAL]))
            .all()
        )

    logger.info(f"Processing daily morning reports for {len(eligible_users)} eligible users")

    # Process each user with their own isolated database session
    for user in eligible_users:
        try:
            with get_db() as db:
                _generate_daily_report_for_user(db, user)
        except Exception as e:
            logger.error(
                f"Error generating daily morning report for user {user.id}: {e}", exc_info=True
            )


@shared_task(name="daily_evening_report")
def daily_evening_report():
    pass
