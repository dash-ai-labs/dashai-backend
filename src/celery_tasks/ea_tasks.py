import datetime
import logging
import os
from typing import List
from celery import shared_task
from llama_index.core.output_parsers import PydanticOutputParser

from openai import BaseModel

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


@shared_task(name="daily_morning_report")
def daily_morning_report():
    with get_db() as db:
        users = db.query(User).all()
        for user in users:
            if (
                user.membership_status == MembershipStatus.ACTIVE
                or user.membership_status == MembershipStatus.TRIAL
            ):
                try:

                    daily_report = DailyReport(
                        user_id=user.id,
                        daily_report_type=DailyReportType.MORNING,
                        actionable_email_ids=[],
                        information_email_ids=[],
                    )
                    db.add(daily_report)
                    db.commit()

                    date_threshold = datetime.datetime.now() - datetime.timedelta(hours=12)
                    if (
                        earlier_report := db.query(DailyReport)
                        .filter(
                            DailyReport.user_id == user.id,
                            DailyReport.daily_report_type == DailyReportType.MORNING,
                            DailyReport.created_at > date_threshold,
                        )
                        .first()
                    ):
                        # Use the earlier report's sent_at time if it exists, otherwise use created_at
                        if earlier_report.sent_at is not None:
                            date_threshold = earlier_report.sent_at
                        else:
                            date_threshold = earlier_report.created_at
                    email_account_ids = [
                        id_tuple[0]
                        for id_tuple in db.query(EmailAccount.id)
                        .filter(EmailAccount.user_id == user.id)
                        .values(EmailAccount.id)
                    ]
                    actionable_emails = (
                        db.query(Email)
                        .filter(
                            Email.email_account_id.in_(email_account_ids),
                            Email.categories.overlap(["actionable"]),
                            Email.folder == EmailFolder.INBOX,
                            Email.date >= date_threshold,
                        )
                        .order_by(Email.date.desc())
                        .all()
                    )
                    # Process actionable emails
                    actionable_response, _ = create_daily_report(
                        "\n".join([serialize_email(email) for email in actionable_emails])
                    )

                    # Collect actionable email data
                    actionable_results = []
                    if (
                        actionable_response
                        and hasattr(actionable_response, "results")
                        and len(actionable_response.results) > 0
                    ):
                        for result in actionable_response.results:
                            if isinstance(result.id, list):
                                daily_report.actionable_email_ids.extend(result.id)
                            else:
                                daily_report.actionable_email_ids.append(result.id)
                            actionable_results.append(result)

                    # Process informational emails
                    informational_emails = (
                        db.query(Email)
                        .filter(
                            Email.email_account_id.in_(email_account_ids),
                            Email.categories.overlap(["information"]),
                            Email.folder == EmailFolder.INBOX,
                            Email.date >= date_threshold,
                        )
                        .order_by(Email.date.desc())
                        .all()
                    )

                    informational_response, _ = create_daily_report(
                        "\n".join([serialize_email(email) for email in informational_emails])
                    )

                    # Collect informational email data
                    informational_results = []
                    if (
                        informational_response
                        and hasattr(informational_response, "results")
                        and len(informational_response.results) > 0
                    ):
                        for result in informational_response.results:
                            if isinstance(result.id, list):
                                daily_report.information_email_ids.extend(result.id)
                            else:
                                daily_report.information_email_ids.append(result.id)
                            informational_results.append(result)

                    # Generate text report
                    text_report = f"Hi {user.name}, your morning email report is ready.\n\n"
                    text_report += "Actionable Emails:\n"
                    if actionable_results:
                        for result in actionable_results:
                            text_report += f"\n* {result.summary}"
                    else:
                        text_report += "\n* No actionable emails found"

                    text_report += "\n\nInformational Emails:\n"
                    if informational_results:
                        for result in informational_results:
                            text_report += f"\n* {result.summary}"
                    else:
                        text_report += "\n* No informational emails found"

                    text_report += f"\n\nReport generated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nReport by DashAI"

                    # Generate HTML report using template
                    html_template = load_html_template("morning_report.html")
                    actionable_emails_html = generate_email_list_html(
                        actionable_results, "actionable-item"
                    )
                    informational_emails_html = generate_email_list_html(
                        informational_results, "informational-item"
                    )

                    html_report = html_template.format(
                        user_name=user.name,
                        actionable_emails_content=actionable_emails_html,
                        informational_emails_content=informational_emails_html,
                        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )

                    daily_report.text_report = text_report
                    daily_report.html_report = html_report
                    db.add(daily_report)
                    db.commit()
                    response = send_email(
                        user.email, "Daily Morning Report", text_report, html_report
                    )
                    if response:
                        daily_report.sent_at = datetime.datetime.now()
                        db.add(daily_report)
                        db.commit()
                    else:
                        logger.error(f"Error sending daily morning report to user {user.id}")

                except Exception as e:
                    logger.error(f"Error generating daily morning report for user {user.id}: {e}")


@shared_task(name="daily_evening_report")
def daily_evening_report():
    pass
