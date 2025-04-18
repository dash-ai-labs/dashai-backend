import urllib.parse

import requests
from sqlalchemy.orm import Session

from src.database import get_db
from src.database.token import Token

from src.libs.const import MSFT_CLIENT_ID, MSFT_REDIRECT_URI, MSFT_TENANT_ID, MSFT_CLIENT_SECRET


class OutlookService:
    def __init__(
        self,
        token: Token = None
    ):
        self.scopes = "openid profile email User.Read Mail.Send Mail.ReadWrite Calendars.ReadWrite offline_access"
        if token:
            self.token = token
            self.validate_token()
        

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

    def refresh_token(self):
        url = f"https://login.microsoftonline.com/{MSFT_TENANT_ID}/oauth2/v2.0/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.token.refresh_token,
            "client_id": MSFT_CLIENT_ID,
            "client_secret": MSFT_CLIENT_SECRET,
            "scope": self.scopes,
            "redirect_uri": MSFT_REDIRECT_URI,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(url, data=data, headers=headers)
        return response.json()

    def _update_token(self, session: Session = get_db):
        try:
            with session as db:
                token_response = self.refresh_token()
                self.token.token = token_response["access_token"]
                self.token.refresh_token = token_response["refresh_token"]
                self.token.updated_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            print(f"Error refreshing token: {self.token.id}", e)
            raise e


    def get_user_info(self, token: str):
        url = f"https://graph.microsoft.com/v1.0/me"
        headers = {
            "Authorization": f"Bearer {token}",
        }
        response = requests.get(url, headers=headers)
        return response.json()


    def validate_token(self):
        try:
            self.get_user_info(self.token.token)
        except Exception as e:
            print("Refreshing token")
            self._update_token()
            
