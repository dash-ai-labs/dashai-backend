from datetime import datetime, timedelta

import requests
from azure.core.credentials import AccessToken
from sqlalchemy.orm import Session

from src.database import get_db
from src.database.token import Token
from src.libs.const import (
    MSFT_CLIENT_ID,
    MSFT_CLIENT_SECRET,
    MSFT_REDIRECT_URI,
    MSFT_TENANT_ID,
)


class OutlookToken:
    def __init__(self, token: Token, db: Session = None):
        self.access_token = token.token
        self.refresh_token = token.refresh_token
        self.expires_at = token.expires_at
        self.token = token
        self.db = db
        self.scopes = "openid profile email User.Read Mail.Send Mail.ReadWrite Calendars.ReadWrite offline_access"

    def get_token(self, *scopes, **kwargs):
        if datetime.utcnow().timestamp() > self.expires_at.timestamp() - 60:
            self._refresh_token()
        return AccessToken(self.access_token, self.expires_at)

    def _refresh_token(self):
        url = f"https://login.microsoftonline.com/{MSFT_TENANT_ID}/oauth2/v2.0/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": MSFT_CLIENT_ID,
            "client_secret": MSFT_CLIENT_SECRET,
            "scope": self.scopes,
            "redirect_uri": MSFT_REDIRECT_URI,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(url, data=data, headers=headers)
        token_data = response.json()

        self.access_token = token_data["access_token"]
        self.refresh_token = token_data["refresh_token"]
        self.expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
        self.token.token = self.access_token
        self.token.refresh_token = self.refresh_token
        self.token.expires_at = self.expires_at
        self.db.commit()
