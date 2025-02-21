from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.libs.const import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


class GoogleProfileService:
    def __init__(self, oauth_token, refresh_token):
        self._oauth_token = oauth_token
        self._refresh_token = refresh_token
        creds = Credentials(
            token=self._oauth_token,
            refresh_token=self._refresh_token,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
        )
        self._service = build("oauth2", "v2", credentials=creds)

    def get_profile(self):
        return self._service.userinfo().get().execute()
