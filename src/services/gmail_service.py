from datetime import datetime

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from src.database import get_db
from src.database.token import Token
from src.libs.const import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


class GmailService:

    def __init__(self, token: Token):
        self._oauth_token = token.token
        self._refresh_token = token.refresh_token
        creds = Credentials(
            token=self._oauth_token,
            refresh_token=self._refresh_token,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            token_uri="https://accounts.google.com/o/oauth2/token",
        )

        if not creds or not creds.valid:
            print("Token not valid")
            creds = self.validate_token(cred=creds, token=token)

        self._service = build("gmail", "v1", credentials=creds)

    def validate_token(self, cred, token: Token, session: Session = get_db):
        if cred and cred.expired and cred.refresh_token:
            try:
                cred.refresh(Request())
                with session() as db:
                    token.token = cred.token
                    token.refresh_token = cred.refresh_token
                    token.updated_at = datetime.utcnow()
                return cred
            except RefreshError:
                print("Token refresh failed")

        return cred

    def list_messages(self, user_id="me", q=None):
        result = self._service.users().messages().list(userId=user_id, q=q).execute()
        messages = []
        if "messages" in result:
            messages.extend(result["messages"])
        while "nextPageToken" in result:
            page_token = result["nextPageToken"]
            result = (
                self._service.users()
                .messages()
                .list(userId="me", q=q, pageToken=page_token)
                .execute()
            )
            if "messages" in result:
                messages.extend(result["messages"])
        return messages

    def get_message(self, message_id, user_id="me"):
        return self._service.users().messages().get(userId=user_id, id=message_id).execute()

    def send_message(self, message):
        return self._service.users().messages().send(userId="me", body=message).execute()

    def get_profile(self):
        return self._service.users().getProfile(userId="me").execute()

    def modify_labels(self, message_id, add_labels=None, remove_labels=None):
        body = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels
        return (
            self._service.users().messages().modify(userId="me", id=message_id, body=body).execute()
        )
