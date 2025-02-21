import json

from google_auth_oauthlib.flow import Flow

from src.libs.const import GOOGLE_CLIENT_CONFIG, GOOGLE_REDIRECT_URI


class FlowService:
    def __init__(self, state=None):
        self._flow: Flow = Flow.from_client_config(
            client_config=json.loads(GOOGLE_CLIENT_CONFIG),
            scopes=self.scopes(),
            redirect_uri=f"{GOOGLE_REDIRECT_URI}",
            autogenerate_code_verifier=True,  # <-- ADD THIS HERE
            state=state,
        )

    def authorization_url(self, **kwargs):
        return self._flow.authorization_url(**kwargs)

    def scopes(self):
        return [
            "https://www.googleapis.com/auth/userinfo.email",
            "openid",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/gmail.modify",
        ]

    def credentials(self, **kwargs):
        self._flow.fetch_token(**kwargs)
        return self._flow.credentials
