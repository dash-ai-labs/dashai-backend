import logging
import boto3
from botocore.exceptions import ClientError

from src.libs.const import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# If necessary, replace us-west-2 with the AWS Region you're using for Amazon SES.
AWS_REGION = "us-west-2"
CHARSET = "UTF-8"


# Create a new SES resource and specify a region.
client = boto3.client(
    "ses",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_email(
    recipient: str, subject: str, body_text: str, body_html: str, sender: str = "daily@getdash.ai"
):
    # Try to send the email.
    try:
        # Provide the contents of the email.
        response = client.send_email(
            Destination={
                "ToAddresses": [
                    recipient,
                ],
            },
            Message={
                "Body": {
                    "Text": {
                        "Data": body_text,
                    },
                    "Html": {
                        "Data": body_html,
                        "Charset": CHARSET,
                    },
                },
                "Subject": {
                    "Data": subject,
                },
            },
            Source=sender,
        )
    except ClientError as e:
        logger.error(e.response["Error"]["Message"])
        return False

    logger.info(f"Email sent! Message ID: {response['MessageId']}")
    return True
