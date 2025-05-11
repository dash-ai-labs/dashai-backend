import urllib.parse

import requests
from fastapi import HTTPException
from kiota_abstractions.base_request_configuration import RequestConfiguration
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.message import Message
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.users.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
    SendMailPostRequestBody,
)
from msgraph.graph_service_client import GraphServiceClient

from src.database.token import Token
from src.libs.const import (
    MSFT_CLIENT_ID,
    MSFT_CLIENT_SECRET,
    MSFT_REDIRECT_URI,
    MSFT_TENANT_ID,
)
from src.libs.types import EmailData, EmailFolder

from .outlook_token import OutlookToken


class OutlookService:
    def __init__(self, token: Token = None, db: requests.Session = None):
        self.scopes = "openid profile email User.Read Mail.Send Mail.ReadWrite Calendars.ReadWrite offline_access"
        self.client = None
        self.folders = {
            EmailFolder.INBOX: "inbox",
            EmailFolder.SENT: "sentitems",
            EmailFolder.DRAFTS: "drafts",
            EmailFolder.TRASH: "deleteditems",
            EmailFolder.SPAM: "junkemail",
        }
        if token:
            self.token = OutlookToken(token, db)
            self.client = GraphServiceClient(credentials=self.token)

    def authorize_url(self, state: str = None, code_challenge: str = None):
        encoded_scopes = urllib.parse.quote(self.scopes, safe="")
        url = f"https://login.microsoftonline.com/{MSFT_TENANT_ID}/oauth2/v2.0/authorize?client_id={MSFT_CLIENT_ID}&response_type=code&response_mode=query&redirect_uri={MSFT_REDIRECT_URI}&scope={encoded_scopes}"
        if state:
            url += f"&state={state}"
        if code_challenge:
            url += f"&code_challenge={code_challenge}&code_challenge_method=S256"
        return url

    def exchange_code(self, code: str, code_verifier: str):
        url = f"https://login.microsoftonline.com/{MSFT_TENANT_ID}/oauth2/v2.0/token"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": MSFT_REDIRECT_URI,
            "client_id": MSFT_CLIENT_ID,
            "client_secret": MSFT_CLIENT_SECRET,
            "scope": self.scopes,
            "code_verifier": code_verifier,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(url, data=data, headers=headers)
        return response.json()

    async def get_user_info(self, token: str = None):
        if token:
            url = f"https://graph.microsoft.com/v1.0/me"
            headers = {
                "Authorization": f"Bearer {token}",
            }
            response = requests.get(url, headers=headers)
            return response.json()
        elif self.client:
            response = await self.client.me.get()
            return response

    async def list_messages_for_folder(self, folder: EmailFolder, after_datetime_str: str):

        try:
            select_params = [
                "id",
                "createdDateTime",
                "sender",
                "toRecipients",
                "subject",
                "ccRecipients",
                "isRead",
                "body",
                "receivedDateTime",
            ]

            # Initialize query parameters
            query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                select=select_params
            )

            # Only add filter if after_datetime_str is provided
            if after_datetime_str:
                query_params.filter = f"receivedDateTime gt {after_datetime_str}"

            request_configuration = RequestConfiguration(query_parameters=query_params)
            result = await self.client.me.mail_folders.by_mail_folder_id(
                self.folders[folder]
            ).messages.get(request_configuration=request_configuration)
            return result.value
        except Exception as e:
            print("Error listing messages: ", e)
            return []

    async def list_messages(self, after_datetime_str: str):
        try:
            select_params = [
                "id",
                "createdDateTime",
                "sender",
                "toRecipients",
                "subject",
                "ccRecipients",
                "isRead",
                "body",
                "receivedDateTime",
            ]

            # Initialize query parameters
            query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                select=select_params
            )

            # Only add filter if after_datetime_str is provided
            if after_datetime_str:
                query_params.filter = f"receivedDateTime gt {after_datetime_str}"

            request_configuration = RequestConfiguration(query_parameters=query_params)
            result = await self.client.me.messages.get(request_configuration=request_configuration)
            return result.value
        except Exception as e:
            print("Error listing messages: ", e)
            return []

    async def get_message(self, message_id: str):
        try:
            return await self.client.me.messages.by_message_id(message_id).get()
        except Exception as e:
            print("Error getting message: ", e)
            return None

    async def mark_as_read(self, message_id: str):
        try:
            msg_update = Message()
            msg_update.is_read = True
            await self.client.me.messages.by_message_id(message_id).patch(msg_update)
        except Exception as e:
            print("Error marking message as read: ", e)
            return False

    async def mark_as_unread(self, message_id: str):
        try:
            msg_update = Message()
            msg_update.is_read = False
            await self.client.me.messages.by_message_id(message_id).patch(msg_update)
        except Exception as e:
            print("Error marking message as unread: ", e)
            return False

    async def archive(self, message_id: str):
        try:
            msg_update = Message()
            msg_update.destination_id = "Archive"
            await self.client.me.messages.by_message_id(message_id).move(msg_update)
        except Exception as e:
            print("Error archiving message: ", e)
            return False

    async def delete(self, message_id: str):
        try:
            msg_update = Message()
            msg_update.destination_id = "deleteditems"
            await self.client.me.messages.by_message_id(message_id).move(msg_update)
        except Exception as e:
            print("Error deleting message: ", e)
            return False

    async def move_to_inbox(self, message_id: str):
        try:
            msg_update = Message()
            msg_update.destination_id = "inbox"
            await self.client.me.messages.by_message_id(message_id).move(msg_update)
        except Exception as e:
            print("Error moving message to inbox: ", e)
            return False

    async def move_to_spam(self, message_id: str):
        try:
            msg_update = Message()
            msg_update.destination_id = "junkemail"
            await self.client.me.messages.by_message_id(message_id).move(msg_update)
        except Exception as e:
            print("Error moving message to spam: ", e)
            return False

    async def send_email(self, email: EmailData):
        try:
            request_body = SendMailPostRequestBody(
                message=Message(
                    subject=email.subject,
                    body=ItemBody(content=email.body, content_type=BodyType.Html),
                    to_recipients=[
                        Recipient(email_address=EmailAddress(address=to)) for to in email.to
                    ],
                )
            )
            await self.client.me.send_mail.post(request_body)
        except Exception as e:
            print("Error sending email: ", e)
            raise HTTPException(status_code=500, detail="Failed to send email")
